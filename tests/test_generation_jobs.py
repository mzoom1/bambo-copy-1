import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse

import server


class GenerationJobsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        server._JOBS.clear()

    def tearDown(self) -> None:
        server._JOBS.clear()

    def _payload(self) -> dict:
        return {
            "bbox": {"minLon": 7.0, "minLat": 46.0, "maxLon": 7.001, "maxLat": 46.001},
            "physicalSizeMm": 200,
            "rows": 2,
            "columns": 2,
            "vertical_exaggeration": 2.0,
            "base_thickness_mm": 5.0,
            "smoothTerrain": True,
            "flattenSeaLevel": True,
            "includeBuildings": False,
            "includeRoads": False,
            "qualityPreset": "Very Low",
        }

    def _decode_json_response(self, response: JSONResponse) -> dict:
        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return json.loads(body)

    async def _wait_for_job(self, job_id: str, timeout: float = 1.0) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = await server.get_job(job_id)
            payload = self._decode_json_response(response)
            last_payload = payload
            if payload["status"] in {"done", "failed"}:
                return payload
            await asyncio.sleep(0.02)
        self.fail(f"Timed out waiting for job {job_id}. Last payload: {last_payload}")

    async def test_post_generate_returns_202_with_job_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "generated.3mf"

            def fake_generate_puzzle_from_map(**_kwargs):
                output.write_bytes(b"job-output")
                return output

            with patch.object(server, "generate_puzzle_from_map", side_effect=fake_generate_puzzle_from_map):
                response = await server.generate(self._payload())
                self.assertIsInstance(response, JSONResponse)
                self.assertEqual(response.status_code, 202)
                body = self._decode_json_response(response)
                self.assertIn("jobId", body)
                self.assertEqual(body["status"], "queued")

                job_id = body["jobId"]
                status_response = await server.get_job(job_id)
                status_payload = self._decode_json_response(status_response)
                self.assertEqual(status_response.status_code, 200)
                self.assertIn(status_payload["status"], {"queued", "running", "done"})
                self.assertIn("progress", status_payload)

                await self._wait_for_job(job_id)

    async def test_job_status_reaches_done_and_download_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "topopuzzle.3mf"

            def fake_generate_puzzle_from_map(**_kwargs):
                output.write_bytes(b"three-m-f")
                return output

            with patch.object(server, "generate_puzzle_from_map", side_effect=fake_generate_puzzle_from_map):
                response = await server.generate(self._payload())
                job_id = self._decode_json_response(response)["jobId"]

                status_payload = await self._wait_for_job(job_id)
                self.assertEqual(status_payload["status"], "done")
                self.assertEqual(status_payload["progress"], 100)

                download = await server.download_job(job_id)
                self.assertIsInstance(download, FileResponse)
                self.assertEqual(download.status_code, 200)
                self.assertEqual(Path(download.path).read_bytes(), b"three-m-f")
                self.assertIn("attachment;", download.headers["content-disposition"])

    async def test_failed_geometry_job_surfaces_message(self) -> None:
        message = "Failed to generate all puzzle pieces (expected 25, got 8). Geometry intersection failed."

        def fake_generate_puzzle_from_map(**_kwargs):
            raise RuntimeError(message)

        with patch.object(server, "generate_puzzle_from_map", side_effect=fake_generate_puzzle_from_map):
            response = await server.generate(self._payload())
            job_id = self._decode_json_response(response)["jobId"]

            status_payload = await self._wait_for_job(job_id)
            self.assertEqual(status_payload["status"], "failed")
            self.assertEqual(status_payload["progress"], 100)
            self.assertIn(message, status_payload["error"])

            with self.assertRaises(HTTPException) as cm:
                await server.download_job(job_id)
            self.assertEqual(cm.exception.status_code, 409)

    async def test_unknown_job_id_returns_404(self) -> None:
        with self.assertRaises(HTTPException) as status_cm:
            await server.get_job("missing-job")
        self.assertEqual(status_cm.exception.status_code, 404)

        with self.assertRaises(HTTPException) as download_cm:
            await server.download_job("missing-job")
        self.assertEqual(download_cm.exception.status_code, 404)

    async def test_download_requires_completed_job(self) -> None:
        now = server._iso_now()
        server._JOBS["job-running"] = server.GenerationJob(
            job_id="job-running",
            status="running",
            progress=10,
            created_at=now,
            updated_at=now,
            filename="pending.3mf",
        )

        with self.assertRaises(HTTPException) as cm:
            await server.download_job("job-running")
        self.assertEqual(cm.exception.status_code, 409)

    async def test_generate_maps_vertical_exaggeration_and_base_thickness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "generated.3mf"

            def fake_generate_puzzle_from_map(**_kwargs):
                output.write_bytes(b"job-output")
                return output

            with patch.object(server, "generate_puzzle_from_map", side_effect=fake_generate_puzzle_from_map) as call:
                response = await server.generate(self._payload())
                self.assertEqual(response.status_code, 202)
                body = self._decode_json_response(response)
                self.assertIn("jobId", body)
                await self._wait_for_job(body["jobId"])

            kwargs = call.call_args.kwargs
            self.assertEqual(kwargs.get("vertical_exaggeration"), 2.0)
            self.assertEqual(kwargs.get("base_thickness_mm"), 5.0)


if __name__ == "__main__":
    unittest.main()
