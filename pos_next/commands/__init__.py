"""Bench CLI commands for pos_next."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

# .../frappe-bench/apps/pos_next/pos_next/commands/__init__.py -> frappe-bench
BENCH_PATH = Path(__file__).resolve().parents[4]

ERPNEXT_REPO = "https://github.com/frappe/erpnext.git"
ERPNEXT_BRANCH = "version-15"

POSNEXT_PROMOTIONS_APP = "posnext_promotions"
POSNEXT_PROMOTIONS_REPO = "https://github.com/BrainWise-DEV/Promotions.git"
POSNEXT_PROMOTIONS_BRANCH = "main"

REQUIRED_SITE_APPS = ("erpnext",)


def _run(command: list[str]) -> None:
	"""Print and run a command from the bench root (live stdout/stderr)."""
	click.echo(f"$ {' '.join(command)}")
	result = subprocess.run(command, cwd=BENCH_PATH)
	if result.returncode != 0:
		raise click.ClickException(
			f"Command failed with exit code {result.returncode}: {' '.join(command)}"
		)


def _is_app_in_bench(app_name: str) -> bool:
	return (BENCH_PATH / "apps" / app_name).is_dir()


def _site_exists(site: str) -> bool:
	return (BENCH_PATH / "sites" / site / "site_config.json").is_file()


def _is_app_on_site(site: str, app_name: str) -> bool:
	result = subprocess.run(
		["bench", "--site", site, "list-apps"],
		cwd=BENCH_PATH,
		text=True,
		capture_output=True,
	)
	if result.returncode != 0:
		detail = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
		raise click.ClickException(
			f"Could not list apps for site '{site}': {detail}"
		)
	installed = {line.strip().split()[0] for line in result.stdout.splitlines() if line.strip()}
	return app_name in installed


def _ensure_app(
	site: str,
	app_name: str,
	repo_url: str | None = None,
	branch: str | None = None,
) -> None:
	if _is_app_in_bench(app_name):
		click.echo(f"Skipping get-app for {app_name}: already present under apps/")
	else:
		if not repo_url:
			raise click.ClickException(
				f"App '{app_name}' is not in apps/ and no repository URL was provided."
			)
		cmd = ["bench", "get-app", repo_url]
		if branch:
			cmd.extend(["--branch", branch])
		_run(cmd)

	if _is_app_on_site(site, app_name):
		click.echo(f"Skipping install-app for {app_name}: already installed on site '{site}'")
	else:
		_run(["bench", "--site", site, "install-app", app_name])


def _check_required_site_apps(site: str, required_apps: tuple[str, ...]) -> None:
	missing = [app for app in required_apps if not _is_app_on_site(site, app)]
	if missing:
		raise click.ClickException(
			"Cannot install pos_next: required site app(s) missing: "
			+ ", ".join(missing)
		)


@click.command("bootstrap")
@click.option("--site", required=True, help="Site name to install apps on")
@click.option(
	"--with-posnext-promotions",
	is_flag=True,
	default=False,
	help="Also get and install posnext_promotions (default: skip)",
)
def bootstrap(site: str, with_posnext_promotions: bool) -> None:
	"""Ensure pos_next dependency apps exist on the bench and site."""
	click.echo(f"Bootstrapping dependencies for site '{site}' (bench: {BENCH_PATH})")

	if not _site_exists(site):
		raise click.ClickException(
			f"Site '{site}' does not exist under {BENCH_PATH / 'sites'}. "
			"Create the site first, or pass an existing --site name."
		)

	_ensure_app(site, "erpnext", repo_url=ERPNEXT_REPO, branch=ERPNEXT_BRANCH)

	if with_posnext_promotions:
		_ensure_app(
			site,
			POSNEXT_PROMOTIONS_APP,
			repo_url=POSNEXT_PROMOTIONS_REPO,
			branch=POSNEXT_PROMOTIONS_BRANCH,
		)
	else:
		click.echo(
			f"Skipping {POSNEXT_PROMOTIONS_APP}: pass --with-posnext-promotions to install"
		)

	_check_required_site_apps(site, REQUIRED_SITE_APPS)
	if _is_app_on_site(site, "pos_next"):
		click.echo(f"Skipping install-app for pos_next: already installed on site '{site}'")
	else:
		if not _is_app_in_bench("pos_next"):
			raise click.ClickException(
				"pos_next is not present under apps/; get the app onto the bench first."
			)
		_run(["bench", "--site", site, "install-app", "pos_next"])

	click.echo("Bootstrap complete.")


commands = [bootstrap]
