import json
import asyncio
import unittest
from unittest.mock import patch

import server
import topomap_to_puzzle_3mf as m


class TopomapHardFailTests(unittest.TestCase):
    def test_validate_piece_count_raises_clear_error(self):
        with self.assertRaisesRegex(
            RuntimeError,
            r"Failed to generate all puzzle pieces \(expected 4, got 3\)\. Geometry intersection failed\."
        ):
            m._validate_piece_count(3, expected=4)

    def test_generate_endpoint_propagates_geometry_message_as_http_500(self):
        payload = {
            "bbox": {"minLon": 0.0, "minLat": 0.0, "maxLon": 1.0, "maxLat": 1.0},
            "physicalSizeMm": 150,
            "rows": 2,
            "columns": 2,
            "zScale": 1.5,
            "smoothTerrain": True,
            "flattenSeaLevel": True,
            "includeBuildings": False,
            "includeRoads": False,
        }

        async def invoke():
            with patch.object(server, "generate_puzzle_from_map", side_effect=RuntimeError(
                "Failed to generate all puzzle pieces (expected 4, got 3). Geometry intersection failed."
            )):
                response = await server.generate(payload)
                self.assertEqual(response.status_code, 202)
                body = response.body.decode("utf-8") if isinstance(response.body, bytes) else response.body
                job_id = json.loads(body)["jobId"]
                await asyncio.sleep(0.05)
                status_response = await server.get_job(job_id)
                status_body = status_response.body.decode("utf-8") if isinstance(status_response.body, bytes) else status_response.body
                return json.loads(status_body)

        status_payload = asyncio.run(invoke())
        self.assertEqual(status_payload["status"], "failed")
        self.assertIn("Failed to generate all puzzle pieces", status_payload["error"])


if __name__ == '__main__':
    unittest.main()
