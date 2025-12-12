#!/usr/bin/env python
"""
Wrapper script to run pytest with Cloudflare Access headers for ReportPortal.
This patches the requests library to add CF-Access headers before pytest-reportportal makes any requests.
"""
import os
import sys

# Patch requests before importing pytest or reportportal
cf_client_id = os.getenv("RP_CF_ACCESS_CLIENT_ID")
cf_client_secret = os.getenv("RP_CF_ACCESS_CLIENT_SECRET")

if cf_client_id and cf_client_secret:
    import requests
    
    # Store the original request method
    original_request = requests.Session.request
    
    def request_with_cf_headers(self, method, url, **kwargs):
        """Add Cloudflare Access headers to ReportPortal requests."""
        if 'reportportal-dev.anacondaconnect.com' in str(url):
            headers = kwargs.get('headers', {})
            if not isinstance(headers, dict):
                headers = dict(headers) if headers else {}
            headers['CF-Access-Client-Id'] = cf_client_id
            headers['CF-Access-Client-Secret'] = cf_client_secret
            kwargs['headers'] = headers
        return original_request(self, method, url, **kwargs)
    
    # Apply the patch
    requests.Session.request = request_with_cf_headers
    print("Cloudflare Access headers configured for ReportPortal", file=sys.stderr)

# Now import and run pytest with all arguments passed through
import pytest

if __name__ == "__main__":
    sys.exit(pytest.main())

