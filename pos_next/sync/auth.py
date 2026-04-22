# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""API key/secret transport auth against central."""

import requests

from pos_next.sync.exceptions import SyncTransportError


class SyncSession:
	"""
	HTTP client for central sync APIs using Frappe API key auth.
	"""

	def __init__(self, central_url, api_key, api_secret):
		self.central_url = central_url.rstrip("/")
		self.api_key = api_key
		self.api_secret = api_secret

	def _headers(self):
		return {"Authorization": f"token {self.api_key}:{self.api_secret}"}

	def post(self, path, data=None, json=None):
		"""Authenticated POST using API key/secret headers."""
		url = f"{self.central_url}{path}"
		try:
			resp = requests.post(
				url,
				data=data,
				json=json,
				headers=self._headers(),
			)
		except requests.RequestException as e:
			raise SyncTransportError(f"POST request failed for {path}: {e}")
		return resp

	def get(self, path, params=None):
		"""Authenticated GET using API key/secret headers."""
		url = f"{self.central_url}{path}"
		try:
			resp = requests.get(
				url,
				params=params,
				headers=self._headers(),
			)
		except requests.RequestException as e:
			raise SyncTransportError(f"GET request failed for {path}: {e}")
		return resp
