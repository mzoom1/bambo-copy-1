import { useCallback, useEffect, useMemo, useState } from 'react';

import type { BBoxState, GridSize, JobStatus, QualityPreset } from '../types';
import { downloadCompletedJob, fetchJobStatus, submitGenerationJob } from '../utils/api';
import { normalizeGenerationErrorMessage } from '../utils/geo';

type UseGenerationJobArgs = {
  apiBaseUrl: string;
  bboxBounds: BBoxState | null;
  physicalSize: number;
  gridSize: GridSize;
  qualityPreset: QualityPreset;
  zScale: number;
  smoothTerrain: boolean;
  flattenSeaLevel: boolean;
  includeBuildings: boolean;
  includeRoads: boolean;
};

type UseGenerationJobResult = {
  generationSteps: string[];
  generationStepIndex: number;
  generationReady: boolean;
  generationError: string | null;
  activeJobId: string | null;
  uiLocked: boolean;
  handleGenerate: () => void;
  dismissError: () => void;
  retry: () => void;
};

export function useGenerationJob(args: UseGenerationJobArgs): UseGenerationJobResult {
  const {
    apiBaseUrl,
    bboxBounds,
    physicalSize,
    gridSize,
    qualityPreset,
    zScale,
    smoothTerrain,
    flattenSeaLevel,
    includeBuildings,
    includeRoads,
  } = args;

  const [generationStepIndex, setGenerationStepIndex] = useState<number>(-1);
  const [generationReady, setGenerationReady] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [pendingDownload, setPendingDownload] = useState<{ blob: Blob; fileName: string } | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const generationSteps = useMemo(
    () => [
      'Submitting generation job...',
      'Generating full map model...',
      'Slicing mesh into puzzle grid...',
      'Packing multi-color 3MF...',
      'Done! Download starting.',
    ],
    [],
  );

  const pieces = useMemo(() => {
    const [xRaw, yRaw] = gridSize.split('x');
    const piecesX = Number(xRaw) || 1;
    const piecesY = Number(yRaw) || 1;
    return { piecesX, piecesY };
  }, [gridSize]);

  const submitGeneration = useCallback(async (): Promise<string> => {
    if (!bboxBounds) {
      throw new Error('Please draw a selection box first.');
    }

    const payload = {
      bbox: {
        minLon: Math.min(bboxBounds.west, bboxBounds.east),
        minLat: Math.min(bboxBounds.south, bboxBounds.north),
        maxLon: Math.max(bboxBounds.west, bboxBounds.east),
        maxLat: Math.max(bboxBounds.south, bboxBounds.north),
      },
      physicalSizeMm: physicalSize,
      rows: pieces.piecesY,
      columns: pieces.piecesX,
      qualityPreset,
      vertical_exaggeration: zScale,
      zScale,
      base_thickness_mm: 5.0,
      smoothTerrain,
      flattenSeaLevel,
      includeBuildings,
      includeRoads,
    };

    const response = await submitGenerationJob(apiBaseUrl, payload);
    return response.jobId;
  }, [
    apiBaseUrl,
    bboxBounds,
    flattenSeaLevel,
    includeBuildings,
    includeRoads,
    physicalSize,
    pieces.piecesX,
    pieces.piecesY,
    qualityPreset,
    smoothTerrain,
    zScale,
  ]);

  const uiLocked = generationStepIndex >= 0 || generationReady;

  const handleGenerate = useCallback(() => {
    if (!bboxBounds || uiLocked) return;

    setGenerationError(null);
    setGenerationReady(false);
    setPendingDownload(null);
    setGenerationStepIndex(0);
    setActiveJobId(null);

    void (async () => {
      try {
        const jobId = await submitGeneration();
        setActiveJobId(jobId);
      } catch (err) {
        const rawMessage = err instanceof Error ? err.message : 'Generation failed.';
        const message = normalizeGenerationErrorMessage(rawMessage);
        setGenerationError(message);
        setGenerationStepIndex(-1);
        setGenerationReady(false);
        setPendingDownload(null);
        setActiveJobId(null);
      }
    })();
  }, [bboxBounds, submitGeneration, uiLocked]);

  useEffect(() => {
    if (!activeJobId) return;

    let cancelled = false;
    let timeoutHandle: number | null = null;

    const pollJob = async () => {
      try {
        for (;;) {
          const job = (await fetchJobStatus(apiBaseUrl, activeJobId)) as JobStatus;
          if (cancelled) return;

          if (job.status === 'failed') {
            throw new Error(job.error || 'Generation failed.');
          }

          if (job.status === 'done') {
            const fallbackName = `topopuzzle_${pieces.piecesY}x${pieces.piecesX}_${physicalSize}mm.3mf`;
            const result = await downloadCompletedJob(apiBaseUrl, activeJobId, fallbackName);
            if (cancelled) return;
            setPendingDownload(result);
            setActiveJobId(null);
            return;
          }

          timeoutHandle = window.setTimeout(() => {
            timeoutHandle = null;
            void pollJob();
          }, 1500);
          return;
        }
      } catch (err) {
        if (cancelled) return;
        const rawMessage = err instanceof Error ? err.message : 'Generation failed.';
        const message = normalizeGenerationErrorMessage(rawMessage);
        setGenerationError(message);
        setGenerationStepIndex(-1);
        setGenerationReady(false);
        setPendingDownload(null);
        setActiveJobId(null);
      }
    };

    void pollJob();

    return () => {
      cancelled = true;
      if (timeoutHandle !== null) {
        window.clearTimeout(timeoutHandle);
      }
    };
  }, [activeJobId, apiBaseUrl, physicalSize, pieces.piecesX, pieces.piecesY]);

  useEffect(() => {
    if (generationStepIndex < 0) return;
    const preDoneMaxIndex = generationSteps.length - 2;

    if (generationStepIndex < preDoneMaxIndex) {
      const timer = window.setTimeout(() => {
        setGenerationStepIndex((prev) => Math.min(prev + 1, preDoneMaxIndex));
      }, 2300);
      return () => window.clearTimeout(timer);
    }

    if (generationStepIndex === preDoneMaxIndex && pendingDownload) {
      const timer = window.setTimeout(() => {
        setGenerationStepIndex(preDoneMaxIndex + 1);
      }, 900);
      return () => window.clearTimeout(timer);
    }
  }, [generationStepIndex, generationSteps.length, pendingDownload]);

  useEffect(() => {
    const doneIndex = generationSteps.length - 1;
    if (generationStepIndex !== doneIndex || !pendingDownload) return;

    const url = URL.createObjectURL(pendingDownload.blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = pendingDownload.fileName;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);

    setPendingDownload(null);
    setGenerationStepIndex(-1);
    setGenerationReady(true);

    const doneTimer = window.setTimeout(() => {
      setGenerationReady(false);
    }, 1600);

    return () => window.clearTimeout(doneTimer);
  }, [generationStepIndex, generationSteps.length, pendingDownload]);

  const dismissError = useCallback(() => {
    setGenerationError(null);
  }, []);

  const retry = useCallback(() => {
    setGenerationError(null);
    handleGenerate();
  }, [handleGenerate]);

  return {
    generationSteps,
    generationStepIndex,
    generationReady,
    generationError,
    activeJobId,
    uiLocked,
    handleGenerate,
    dismissError,
    retry,
  };
}
