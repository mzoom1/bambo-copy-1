import { AnimatePresence, motion } from 'motion/react';
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react';

type GenerationProgressProps = {
  generationSteps: string[];
  generationStepIndex: number;
  generationReady: boolean;
  generationError: string | null;
  onDismissError: () => void;
  onRetry: () => void;
};

export function GenerationProgress({
  generationSteps,
  generationStepIndex,
  generationReady,
  generationError,
  onDismissError,
  onRetry,
}: GenerationProgressProps) {
  return (
    <>
      <AnimatePresence>
        {(generationStepIndex >= 0 || generationReady) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 flex items-center justify-center bg-slate-900/25 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.94, y: 16 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.96, y: 12 }}
              className="w-full max-w-lg mx-4 rounded-2xl border border-white/30 bg-white/90 p-6 shadow-[0_8px_30px_rgb(0,0,0,0.08)]"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="h-10 w-10 rounded-xl bg-slate-900 text-white flex items-center justify-center shadow-[0_8px_18px_rgb(15,23,42,0.22)]">
                  {generationReady ? <CheckCircle2 size={20} /> : <Sparkles size={20} />}
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-800">Terrain Generation Pipeline</h3>
                  <p className="text-xs text-slate-500">Optimized backend 3MF export sequence</p>
                </div>
              </div>

              {generationReady ? (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-700 font-medium flex items-center gap-2">
                  <CheckCircle2 size={18} />
                  Done! Download starting.
                </div>
              ) : (
                <>
                  <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-700 font-medium flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin text-slate-800" />
                    {generationStepIndex >= 0 ? generationSteps[generationStepIndex] : generationSteps[0]}
                  </div>

                  <div className="mt-4 space-y-2">
                    {generationSteps.map((step, idx) => {
                      const isDone = generationStepIndex > idx;
                      const isCurrent = generationStepIndex === idx;
                      return (
                        <div key={step} className="flex items-center gap-3">
                          <div
                            className={`h-5 w-5 rounded-full flex items-center justify-center ${
                              isDone
                                ? 'bg-emerald-100 text-emerald-600'
                                : isCurrent
                                ? 'bg-slate-200 text-slate-800'
                                : 'bg-slate-100 text-slate-300'
                            }`}
                          >
                            {isDone ? <CheckCircle2 size={13} /> : <span className="h-1.5 w-1.5 rounded-full bg-current"></span>}
                          </div>
                          <span className={`text-sm ${isCurrent ? 'text-slate-800 font-medium' : 'text-slate-500'}`}>{step}</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {generationError && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-[60] flex items-center justify-center bg-slate-950/45 backdrop-blur-[6px] px-4"
          >
            <motion.div
              initial={{ scale: 0.96, y: 18 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.98, y: 10 }}
              className="w-full max-w-md rounded-2xl border border-rose-200 bg-white/95 p-6 shadow-[0_18px_50px_rgba(15,23,42,0.18)]"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-100 text-rose-600">
                  <Sparkles size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-semibold text-slate-900">Generation failed</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">{generationError}</p>
                </div>
              </div>

              <div className="mt-5 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={onDismissError}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                >
                  Dismiss
                </button>
                <button
                  type="button"
                  onClick={onRetry}
                  className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
                >
                  Try again
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

