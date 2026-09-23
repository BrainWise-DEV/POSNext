param(
    [string]$ConfigPath = "$PSScriptRoot\config.json"
)

$ErrorActionPreference = "Stop"
$AgentVersion = "0.2.0"

if (-not (Test-Path $ConfigPath)) {
    throw "POSNext Local Agent config not found: $ConfigPath"
}

$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$bindHost = if ($config.BindHost) { [string]$config.BindHost } else { "127.0.0.1" }
$port = if ($config.Port) { [int]$config.Port } else { 17777 }
$token = [string]$config.Token
$allowedOrigins = @($config.AllowedOrigins | ForEach-Object { [string]$_ })
$allowedPrinters = @($config.AllowedPrinters | ForEach-Object { [string]$_ })

if ([string]::IsNullOrWhiteSpace($token)) { throw "Config Token must not be empty." }
if ($bindHost -ne "127.0.0.1" -and $bindHost -ne "localhost") {
    throw "Local Agent is restricted to loopback. Set BindHost to 127.0.0.1 or localhost."
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class POSNextRawPrinter {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public class DOCINFOA {
        [MarshalAs(UnmanagedType.LPStr)] public string pDocName;
        [MarshalAs(UnmanagedType.LPStr)] public string pOutputFile;
        [MarshalAs(UnmanagedType.LPStr)] public string pDataType;
    }

    [DllImport("winspool.Drv", EntryPoint="OpenPrinterA", SetLastError=true, CharSet=CharSet.Ansi, ExactSpelling=true)]
    public static extern bool OpenPrinter(string szPrinter, out IntPtr hPrinter, IntPtr pd);
    [DllImport("winspool.Drv", EntryPoint="ClosePrinter", SetLastError=true, ExactSpelling=true)]
    public static extern bool ClosePrinter(IntPtr hPrinter);
    [DllImport("winspool.Drv", EntryPoint="StartDocPrinterA", SetLastError=true, CharSet=CharSet.Ansi, ExactSpelling=true)]
    public static extern bool StartDocPrinter(IntPtr hPrinter, Int32 level, [In] DOCINFOA di);
    [DllImport("winspool.Drv", EntryPoint="EndDocPrinter", SetLastError=true, ExactSpelling=true)]
    public static extern bool EndDocPrinter(IntPtr hPrinter);
    [DllImport("winspool.Drv", EntryPoint="StartPagePrinter", SetLastError=true, ExactSpelling=true)]
    public static extern bool StartPagePrinter(IntPtr hPrinter);
    [DllImport("winspool.Drv", EntryPoint="EndPagePrinter", SetLastError=true, ExactSpelling=true)]
    public static extern bool EndPagePrinter(IntPtr hPrinter);
    [DllImport("winspool.Drv", EntryPoint="WritePrinter", SetLastError=true, ExactSpelling=true)]
    public static extern bool WritePrinter(IntPtr hPrinter, IntPtr pBytes, Int32 dwCount, out Int32 dwWritten);

    public static void SendBytes(string printerName, byte[] bytes, string documentName) {
        IntPtr hPrinter;
        if (!OpenPrinter(printerName, out hPrinter, IntPtr.Zero)) {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "OpenPrinter failed");
        }
        try {
            var di = new DOCINFOA { pDocName = documentName, pDataType = "RAW", pOutputFile = null };
            if (!StartDocPrinter(hPrinter, 1, di)) {
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "StartDocPrinter failed");
            }
            try {
                if (!StartPagePrinter(hPrinter)) {
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "StartPagePrinter failed");
                }
                try {
                    IntPtr unmanaged = Marshal.AllocCoTaskMem(bytes.Length);
                    try {
                        Marshal.Copy(bytes, 0, unmanaged, bytes.Length);
                        Int32 written;
                        if (!WritePrinter(hPrinter, unmanaged, bytes.Length, out written) || written != bytes.Length) {
                            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "WritePrinter failed");
                        }
                    } finally { Marshal.FreeCoTaskMem(unmanaged); }
                } finally { EndPagePrinter(hPrinter); }
            } finally { EndDocPrinter(hPrinter); }
        } finally { ClosePrinter(hPrinter); }
    }
}
"@

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://$bindHost`:$port/")
$listener.Start()
Write-Host "POSNext Local Agent $AgentVersion listening on http://$bindHost`:$port/"

$recentNonces = @{}
$requestTimes = New-Object System.Collections.Generic.List[datetime]
$lastDrawerOpen = [DateTime]::MinValue

function Write-JsonResponse {
    param($Response, [int]$StatusCode, $Payload, [string]$Origin = "")
    $json = $Payload | ConvertTo-Json -Depth 8 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $Response.StatusCode = $StatusCode
    $Response.ContentType = "application/json; charset=utf-8"
    $Response.Headers["Cache-Control"] = "no-store"
    if ($Origin) {
        $Response.Headers["Access-Control-Allow-Origin"] = $Origin
        $Response.Headers["Vary"] = "Origin"
    }
    $Response.ContentLength64 = $bytes.Length
    $Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Response.OutputStream.Close()
}

function Is-OriginAllowed([string]$Origin) {
    if ([string]::IsNullOrWhiteSpace($Origin)) { return $false }
    return $allowedOrigins -contains $Origin
}

function Is-PrinterAllowed([string]$PrinterName) {
    if ([string]::IsNullOrWhiteSpace($PrinterName)) { return $false }
    if ($allowedPrinters.Count -eq 0) { return $false }
    return $allowedPrinters -contains $PrinterName
}

function Test-RateLimit {
    $now = [DateTime]::UtcNow
    $cutoff = $now.AddMinutes(-1)
    for ($i = $requestTimes.Count - 1; $i -ge 0; $i--) {
        if ($requestTimes[$i] -lt $cutoff) { $requestTimes.RemoveAt($i) }
    }
    if ($requestTimes.Count -ge 120) { return $false }
    $requestTimes.Add($now)
    return $true
}

function Get-RequestBody($Request) {
    $reader = New-Object IO.StreamReader($Request.InputStream, $Request.ContentEncoding)
    try {
        $raw = $reader.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($raw)) { return @{} }
        return $raw | ConvertFrom-Json
    } finally { $reader.Close() }
}

function Test-Auth($Request) {
    $provided = [string]$Request.Headers["X-POSNext-Token"]
    if ($provided -cne $token) { return $false }

    $nonce = [string]$Request.Headers["X-POSNext-Nonce"]
    if ([string]::IsNullOrWhiteSpace($nonce)) { return $false }
    if ($recentNonces.ContainsKey($nonce)) { return $false }
    $recentNonces[$nonce] = [DateTime]::UtcNow

    $cutoff = [DateTime]::UtcNow.AddMinutes(-5)
    foreach ($key in @($recentNonces.Keys)) {
        if ($recentNonces[$key] -lt $cutoff) { $recentNonces.Remove($key) }
    }
    return $true
}

function Get-InstalledPrinters {
    return @(Get-CimInstance Win32_Printer | Sort-Object Name | ForEach-Object { $_.Name })
}

function Send-TestPrint([string]$PrinterName, [string]$TerminalId) {
    $esc = [byte]27
    $init = [byte[]]@($esc, 64)
    $text = "POSNext Local Agent Test`r`nTerminal: $TerminalId`r`nPrinter: $PrinterName`r`nStatus: OK`r`n`r`n`r`n"
    $body = [Text.Encoding]::ASCII.GetBytes($text)
    $payload = New-Object byte[] ($init.Length + $body.Length)
    [Array]::Copy($init, 0, $payload, 0, $init.Length)
    [Array]::Copy($body, 0, $payload, $init.Length, $body.Length)
    [POSNextRawPrinter]::SendBytes($PrinterName, $payload, "POSNext Local Agent Test")
}

function Open-Drawer([string]$PrinterName, [string]$Profile) {
    switch ($Profile) {
        "escpos_drawer_1" { $bytes = [byte[]]@(27,112,0,25,250) }
        "escpos_drawer_2" { $bytes = [byte[]]@(27,112,1,25,250) }
        "star" { throw "Star Compatible drawer command is not enabled. Configure a verified vendor command before using it." }
        default { throw "Unsupported cash drawer command profile: $Profile" }
    }
    [POSNextRawPrinter]::SendBytes($PrinterName, $bytes, "POSNext Cash Drawer")
}

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        $origin = [string]$request.Headers["Origin"]

        try {
            if (-not (Is-OriginAllowed $origin)) {
                Write-JsonResponse $response 403 @{ success = $false; message = "Origin is not allowed." }
                continue
            }

            if ($request.HttpMethod -eq "OPTIONS") {
                $response.StatusCode = 204
                $response.Headers["Access-Control-Allow-Origin"] = $origin
                $response.Headers["Access-Control-Allow-Headers"] = "Content-Type, X-POSNext-Token, X-POSNext-Nonce"
                $response.Headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                $response.Headers["Access-Control-Allow-Private-Network"] = "true"
                $response.Headers["Vary"] = "Origin"
                $response.OutputStream.Close()
                continue
            }

            if (-not (Test-RateLimit)) {
                Write-JsonResponse $response 429 @{ success = $false; message = "Local Agent request rate limit exceeded." } $origin
                continue
            }
            if (-not (Test-Auth $request)) {
                Write-JsonResponse $response 401 @{ success = $false; message = "Local Agent authentication failed." } $origin
                continue
            }

            $path = $request.Url.AbsolutePath.ToLowerInvariant()
            if ($request.HttpMethod -eq "GET" -and $path -eq "/health") {
                $printers = Get-InstalledPrinters
                Write-JsonResponse $response 200 @{
                    success = $true
                    version = $AgentVersion
                    printer_count = $printers.Count
                    allowed_printer_count = $allowedPrinters.Count
                } $origin
                continue
            }

            if ($request.HttpMethod -eq "GET" -and $path -eq "/printers") {
                $installed = Get-InstalledPrinters
                $printers = @($installed | Where-Object { $allowedPrinters -contains $_ })
                Write-JsonResponse $response 200 @{ success = $true; printers = $printers } $origin
                continue
            }

            if ($request.HttpMethod -eq "POST" -and $path -eq "/test-print") {
                $body = Get-RequestBody $request
                $printer = [string]$body.printer_name
                if (-not (Is-PrinterAllowed $printer)) { throw "Printer is not allowlisted in Local Agent config: $printer" }
                Send-TestPrint $printer ([string]$body.terminal_id)
                Write-JsonResponse $response 200 @{ success = $true; printer_name = $printer } $origin
                continue
            }

            if ($request.HttpMethod -eq "POST" -and $path -eq "/drawer/open") {
                if (([DateTime]::UtcNow - $lastDrawerOpen).TotalMilliseconds -lt 1000) {
                    Write-JsonResponse $response 429 @{ success = $false; message = "Cash drawer request rate limit exceeded." } $origin
                    continue
                }
                $body = Get-RequestBody $request
                $printer = [string]$body.printer_name
                if (-not (Is-PrinterAllowed $printer)) { throw "Printer is not allowlisted in Local Agent config: $printer" }
                Open-Drawer $printer ([string]$body.command_profile)
                $lastDrawerOpen = [DateTime]::UtcNow
                Write-JsonResponse $response 200 @{
                    success = $true
                    printer_name = $printer
                    terminal_id = [string]$body.terminal_id
                } $origin
                continue
            }

            Write-JsonResponse $response 404 @{ success = $false; message = "Unknown Local Agent endpoint." } $origin
        } catch {
            try { Write-JsonResponse $response 500 @{ success = $false; message = $_.Exception.Message } $origin }
            catch { try { $response.Abort() } catch {} }
        }
    }
} finally {
    if ($listener.IsListening) { $listener.Stop() }
    $listener.Close()
}
