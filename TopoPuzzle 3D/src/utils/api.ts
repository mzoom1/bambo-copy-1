import type { JobResponse, JobStatus } from '../types';

export async function extractApiErrorMessage(response: Response): Promise<string> {
  const fallback = `HTTP ${response.status}`;
  const bodyText = await response.text().catch(() => '');
  const trimmed = bodyText.trim();
  if (!trimmed) return fallback;

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      const payload = JSON.parse(trimmed) as { detail?: unknown };
      if (typeof payload?.detail === 'string' && payload.detail.trim()) {
        return payload.detail;
      }
      if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
        const first = payload.detail[0] as { msg?: string } | undefined;
        if (first?.msg) return first.msg;
      }
      if (payload?.detail) return JSON.stringify(payload.detail);
    } catch {
      // fall through to raw body text
    }
  }

  return trimmed;
}

export async function submitGenerationJob(apiBaseUrl: string, payload: unknown): Promise<JobResponse> {
  const response = await fetch(`${apiBaseUrl}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await extractApiErrorMessage(response));
  }

  const submitPayload = (await response.json()) as JobResponse;
  if (!submitPayload?.jobId) {
    throw new Error('Backend did not return a job id.');
  }
  return submitPayload;
}

export async function fetchJobStatus(apiBaseUrl: string, jobId: string): Promise<JobStatus> {
  const response = await fetch(`${apiBaseUrl}/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    throw new Error(await extractApiErrorMessage(response));
  }
  return (await response.json()) as JobStatus;
}

export async function downloadCompletedJob(
  apiBaseUrl: string,
  jobId: string,
  fallbackName: string,
): Promise<{ blob: Blob; fileName: string }> {
  const downloadResponse = await fetch(`${apiBaseUrl}/jobs/${encodeURIComponent(jobId)}/download`);
  if (!downloadResponse.ok) {
    throw new Error(await extractApiErrorMessage(downloadResponse));
  }

  const blob = await downloadResponse.blob();
  if (!blob || blob.size === 0) {
    throw new Error('Backend returned an empty 3MF file.');
  }

  const contentDisposition = downloadResponse.headers.get('content-disposition') || '';
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  const asciiMatch = contentDisposition.match(/filename="?([^"]+)"?/i);

  let fileName = fallbackName;
  if (utf8Match?.[1]) {
    fileName = decodeURIComponent(utf8Match[1]);
  } else if (asciiMatch?.[1]) {
    fileName = asciiMatch[1];
  }

  return { blob, fileName };
}

