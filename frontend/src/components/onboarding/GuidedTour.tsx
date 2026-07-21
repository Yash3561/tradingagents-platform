import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ArrowLeft, X, Compass } from "lucide-react";
import { api } from "../../lib/api";
import { EASE, DUR } from "../../lib/motion";

/** Any page can re-open the tour without prop-drilling — mirrors how
 * BrokerStatusCard does its own independent polling rather than reading
 * from a shared store; the codebase has no global-state library wired up,
 * so a plain window event is the right amount of machinery for one signal. */
export const OPEN_TOUR_EVENT = "open-tour";

interface Step {
  id: string;
  /** data-tour attribute value on the target element, or null for a
   * centered, non-spotlighted card (welcome/closing steps). */
  target: string | null;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    id: "welcome",
    target: null,
    title: "Welcome to TradingAgents",
    body: "A quick, minute-long tour of how the platform is laid out. You can skip at any point — Settings has a \"Take the tour again\" button if you want it back later.",
  },
  {
    id: "nav-trading",
    target: '[data-tour="nav-trading"]',
    title: "Trading",
    body: "Markets, your Watchlist, News and the Calendar for context, the Scanner that finds candidates, Agent Hub to run the AI pipeline on one ticker by hand, and the Options Desk.",
  },
  {
    id: "nav-portfolio",
    target: '[data-tour="nav-portfolio"]',
    title: "Portfolio",
    body: "Live positions and your equity curve, the full Trade History with the AI's reasoning behind every trade, Orders, smart Alerts, and a Backtesting sandbox.",
  },
  {
    id: "nav-intelligence",
    target: '[data-tour="nav-intelligence"]',
    title: "Intelligence",
    body: "Analytics grades the AI's own performance, Track Record is the public proof page, Strategy shows the live risk rules, How It Works explains the whole system end to end, and Learn is a glossary of every term used here.",
  },
  {
    id: "broker-status",
    target: '[data-tour="broker-status"]',
    title: "Connect your broker",
    body: "Paste your Alpaca paper-trading API keys in Settings so the platform can actually place trades in your own paper account. Nothing trades until this is connected — analysis works either way.",
  },
  {
    id: "header-clock",
    target: '[data-tour="header-clock"]',
    title: "Market clock",
    body: "A live market-open indicator in Eastern Time. Scheduled scans only run while the market's open.",
  },
  {
    id: "header-notifications",
    target: '[data-tour="header-notifications"]',
    title: "Notifications",
    body: "Every trade entry, stop-loss, take-profit, and scan result shows up here as it happens.",
  },
  {
    id: "done",
    target: null,
    title: "You're set",
    body: "Pick a Strategy Engine and connect your broker in Settings, and you're live. For the full picture — the 7-agent pipeline and all six strategy engines — head to How It Works next.",
  },
];

const CARD_WIDTH = 340;
const PADDING = 16;
const SPOTLIGHT_PAD = 8;

/** Scrolls the target into view first — the sidebar nav is its own
 * scrollable container, so a lower group (Intelligence) can have a real
 * size but sit below the fold with nothing to spotlight on screen. */
function elementRectScrolled(selector: string): DOMRect | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  el.scrollIntoView({ block: "nearest", inline: "nearest" });
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return null;
  return rect;
}

function elementRect(selector: string): DOMRect | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return null; // hidden at this breakpoint
  return rect;
}

/** Scan forward/backward from `from` for the next step whose target either
 * doesn't need one, or is actually present and visible right now — narrow
 * viewports hide some nav groups (mobile sidebar) and header items, so the
 * tour should shorten gracefully instead of spotlighting nothing. */
function findValidIndex(from: number, dir: 1 | -1): number {
  let i = from;
  while (i >= 0 && i < STEPS.length) {
    const step = STEPS[i];
    if (step.target === null || elementRect(step.target) !== null) return i;
    i += dir;
  }
  return dir === 1 ? STEPS.length - 1 : 0;
}

// Conservative — body copy runs up to ~4 lines plus header/footer chrome.
// Better to clamp early than let the card's bottom run off-screen; the card
// itself also carries a maxHeight + scroll as a last-resort safety net.
const CARD_MAX_HEIGHT = 320;

function cardPosition(rect: DOMRect | null): { top: number; left: number } | null {
  if (!rect) return null;
  const maxTop = Math.max(PADDING, window.innerHeight - CARD_MAX_HEIGHT - PADDING);
  const maxLeft = Math.max(PADDING, window.innerWidth - CARD_WIDTH - PADDING);
  const roomRight = window.innerWidth - rect.right;

  const raw = roomRight >= CARD_WIDTH + PADDING * 2
    ? { left: rect.right + PADDING, top: rect.top }
    // Not enough room to the right (narrow viewport, or a right-edge header
    // icon) — place below instead.
    : { left: rect.left - CARD_WIDTH / 2, top: rect.bottom + PADDING };

  // Hard clamp regardless of which branch chose the raw position — the
  // heuristic above picks a *side*, this guarantees it's on-screen. A
  // header item near the right edge (market clock, bell) previously ran
  // the card off-screen entirely because the branch check alone wasn't a
  // reliable enough guarantee.
  return {
    left: Math.min(Math.max(raw.left, PADDING), maxLeft),
    top: Math.min(Math.max(raw.top, PADDING), maxTop),
  };
}

export default function GuidedTour() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const checkedRef = useRef(false);

  const persistCompleted = useCallback(() => {
    api.post("/settings/", { onboarding_tour_completed: true }).catch(() => {});
  }, []);

  // Auto-show once for any user who hasn't finished/skipped it yet.
  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;
    api.get("/settings/")
      .then(({ data }) => {
        if (data?.onboarding_tour_completed !== true) {
          setStepIdx(0);
          setOpen(true);
        }
      })
      .catch(() => {});
  }, []);

  // Manual re-launch from Settings / How It Works.
  useEffect(() => {
    const handler = () => { setStepIdx(0); setOpen(true); };
    window.addEventListener(OPEN_TOUR_EVENT, handler);
    return () => window.removeEventListener(OPEN_TOUR_EVENT, handler);
  }, []);

  // Recompute the spotlighted element's rect on step change and resize.
  useEffect(() => {
    if (!open) return;
    const step = STEPS[stepIdx];
    const update = () => setRect(step.target ? elementRectScrolled(step.target) : null);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [open, stepIdx]);

  if (!open) return null;

  const step = STEPS[stepIdx];
  const isFirst = stepIdx === 0;
  const isLast = stepIdx === STEPS.length - 1;

  const goNext = () => {
    if (isLast) {
      persistCompleted();
      setOpen(false);
      return;
    }
    setStepIdx(i => findValidIndex(i + 1, 1));
  };
  const goBack = () => setStepIdx(i => findValidIndex(i - 1, -1));
  const skip = () => {
    persistCompleted();
    setOpen(false);
  };
  const goHowItWorks = () => {
    persistCompleted();
    setOpen(false);
    navigate("/how-it-works");
  };

  const pos = cardPosition(rect);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: DUR.base, ease: EASE }}
        className="fixed inset-0 z-[60] pointer-events-none"
      >
        {/* Backdrop with a cutout over the spotlighted element */}
        <svg className="absolute inset-0 w-full h-full">
          <defs>
            <mask id="tour-mask">
              <rect x="0" y="0" width="100%" height="100%" fill="white" />
              {rect && (
                <rect
                  x={rect.left - SPOTLIGHT_PAD}
                  y={rect.top - SPOTLIGHT_PAD}
                  width={rect.width + SPOTLIGHT_PAD * 2}
                  height={rect.height + SPOTLIGHT_PAD * 2}
                  rx={10}
                  fill="black"
                />
              )}
            </mask>
          </defs>
          <rect x="0" y="0" width="100%" height="100%" fill="black" fillOpacity={0.72} mask="url(#tour-mask)" />
          {rect && (
            <rect
              x={rect.left - SPOTLIGHT_PAD}
              y={rect.top - SPOTLIGHT_PAD}
              width={rect.width + SPOTLIGHT_PAD * 2}
              height={rect.height + SPOTLIGHT_PAD * 2}
              rx={10}
              fill="none"
              stroke="#2D7DD2"
              strokeWidth={2}
            />
          )}
        </svg>

        {/* Step card — positioning lives on this plain wrapper (not
            animated), because Framer Motion owns the `transform` property
            once `scale` is in the animate/initial set, which silently
            clobbers a manually-set `translate(-50%, -50%)` centering trick
            on the same element. Keep layout and animation on separate
            elements so neither fights the other. */}
        <div
          className="absolute pointer-events-auto"
          style={
            pos
              ? { top: pos.top, left: pos.left, width: CARD_WIDTH }
              : { top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: CARD_WIDTH }
          }
        >
          <motion.div
            key={step.id}
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: DUR.fast, ease: EASE }}
            className="card p-5 shadow-2xl border-accent/30 overflow-y-auto"
            style={{ maxHeight: CARD_MAX_HEIGHT }}
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex items-center gap-2">
                <Compass size={16} className="text-accent shrink-0" />
                <h3 className="text-sm font-semibold text-text-primary">{step.title}</h3>
              </div>
              <button onClick={skip} className="text-text-muted hover:text-text-primary transition-colors shrink-0" aria-label="Skip tour">
                <X size={16} />
              </button>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-4">{step.body}</p>

            <div className="flex items-center justify-between">
              <span className="text-2xs text-text-muted font-mono">{stepIdx + 1} / {STEPS.length}</span>
              <div className="flex items-center gap-2">
                {!isFirst && (
                  <button
                    onClick={goBack}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-text-secondary hover:bg-bg-elevated transition-colors"
                  >
                    <ArrowLeft size={12} /> Back
                  </button>
                )}
                {isLast ? (
                  <button
                    onClick={goHowItWorks}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent text-white hover:bg-accent-bright transition-colors"
                  >
                    How It Works <ArrowRight size={12} />
                  </button>
                ) : (
                  <button
                    onClick={goNext}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent text-white hover:bg-accent-bright transition-colors"
                  >
                    Next <ArrowRight size={12} />
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
