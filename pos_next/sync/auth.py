# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Username/password session login against central."""

import requests

from pos_next.sync.defaults import HTTP_TIMEOUT_SECONDS, LOGIN_TIMEOUT_SECONDS
from pos_next.sync.exceptions import SyncAuthError, SyncTransportError


class SyncSession:
	"""
	Holds a logged-in session against central.

	Login happens lazily on first use. On a 401 response, we automatically
	re-log in once and retry the original request.
	"""

	def __init__(self, central_url, username, password):
		self.central_url = central_url.rstrip("/")
		self.username = username
		self.password = password
		self._sid = None

	def login(self):
		"""POST /api/method/login. Cache sid in memory."""
		if self._sid:
			return
		url = f"{self.central_url}/api/method/login"
		try:
			resp = requests.post(
				url,
				data={"usr": self.username, "pwd": self.password},
				timeout=LOGIN_TIMEOUT_SECONDS,
			)
			resp.raise_for_status()
		except requests.HTTPError as e:
			raise SyncAuthError(f"Login failed for {self.username}: {e}")
		except requests.RequestException as e:
			raise SyncTransportError(f"Login request failed: {e}")
		sid = resp.cookies.get("sid")
		if not sid:
			raise SyncAuthError("Login response did not include sid cookie")
		self._sid = sid

	def _cookies(self):
		return {"sid": self._sid} if self._sid else {}

	def post(self, path, data=None, json=None):
		"""Authenticated POST. On 401, re-login and retry once."""
		self.login()
		url = f"{self.central_url}{path}"
		resp = requests.post(
			url,
			data=data,
			json=json,
			cookies=self._cookies(),
			timeout=HTTP_TIMEOUT_SECONDS,
		)
		if resp.status_code == 401:
			self._sid = None
			self.login()
			resp = requests.post(
				url,
				data=data,
				json=json,
				cookies=self._cookies(),
				timeout=HTTP_TIMEOUT_SECONDS,
			)
		return resp

	def get(self, path, params=None):
		"""Authenticated GET. On 401, re-login and retry once."""
		self.login()
		url = f"{self.central_url}{path}"
		resp = requests.get(
			url,
			params=params,
			cookies=self._cookies(),
			timeout=HTTP_TIMEOUT_SECONDS,
		)
		if resp.status_code == 401:
			self._sid = None
			self.login()
			resp = requests.get(
				url,
				params=params,
				cookies=self._cookies(),
				timeout=HTTP_TIMEOUT_SECONDS,
			)
		return resp

	def logout(self):
		"""POST /api/method/logout. Best-effort; ignore errors."""
		if not self._sid:
			return
		try:
			requests.post(
				f"{self.central_url}/api/method/logout",
				cookies=self._cookies(),
				timeout=LOGIN_TIMEOUT_SECONDS,
			)
		except requests.RequestException:
			pass
		self._sid = None
