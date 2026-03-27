import time
import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TerraPrinterClient:
    def __init__(self, api_key_or_cookie: str = None):
        self.session = requests.Session()
        # Add headers copied from browser DevTools
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://terraprinter.com",
            "Referer": "https://terraprinter.com/",
            # "Cookie": api_key_or_cookie, # Inject session cookie if required
            # "X-CSRF-Token": "extracted_token_here",
        })
        self.base_url = "https://terraprinter.com/api" # Replace with actual endpoint
        
    def generate_3mf(self, payload: dict, output_file: str):
        """
        Sends the generation request, polls for status, and downloads the result.
        """
        logger.info("Submitting generation request...")
        # Endpoint where the form is submitted
        submit_url = f"{self.base_url}/generate" 
        
        try:
            resp = self.session.post(submit_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            job_id = data.get("job_id") # Adjust based on actual response
            if not job_id:
                logger.error("No job ID returned.")
                return
                
            logger.info(f"Job {job_id} started. Polling for completion...")
            
            # Poll for status
            status_url = f"{self.base_url}/jobs/{job_id}/status"
            while True:
                status_resp = self.session.get(status_url)
                status_resp.raise_for_status()
                status_data = status_resp.json()
                
                state = status_data.get("status")
                if state == "completed":
                    download_url = status_data.get("download_url")
                    logger.info(f"Job completed! Downloading from {download_url}...")
                    self._download_file(download_url, output_file)
                    break
                elif state in ["failed", "error"]:
                    logger.error(f"Job failed: {status_data.get('error')}")
                    break
                    
                logger.info(f"Status: {state}. Waiting 5 seconds...")
                time.sleep(5)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API Request failed: {e}")

    def _download_file(self, url: str, dest_path: str):
        # We might need the full URL if it's a relative path
        if url.startswith('/'):
            url = f"https://terraprinter.com{url}"
            
        with self.session.get(url, stream=True) as r:
            r.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"Saved successfully to {dest_path}")

if __name__ == "__main__":
    # Conceptual payload based on DevTools observation
    payload = {
        "bounds": [2.28, 48.84, 2.36, 48.90], # min_lon, min_lat, max_lon, max_lat
        "zScale": 2.0,
        "base_thickness_mm": 5.0,
        "format": "3mf",
        "quality": "high",
        "include_buildings": True,
        "include_roads": True
    }
    
    client = TerraPrinterClient()
    client.generate_3mf(payload, "output_puzzle.3mf")
