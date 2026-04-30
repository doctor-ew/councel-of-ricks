/**
 * Truth-O-Meter — animated SVG semicircle gauge.
 *
 * Renders a 0-100 confidence score from the Arbiter as a 180-degree
 * arc with a swinging needle, themed in the project's R&M-flavored
 * zone scale. Hand-rolled SVG (no chart library) with CSS transitions
 * on the needle's `transform: rotate(...)` and the foreground arc's
 * `stroke-dashoffset`.
 *
 * Score → angle mapping: 0 → -90deg (left), 100 → +90deg (right),
 * i.e. `rotate(score * 1.8 - 90)`.
 *
 * `score === null` is a distinct neutral idle state — needle parked
 * at the +90deg (100) position with no zone label rendered. This is
 * NOT the same as `score === 100`.
 *
 * Zones are externally overridable via the `zones` prop so GH-9
 * (R&M re-skin) can swap color tokens and GH-6 (demo presenter)
 * can override label copy without editing component logic.
 */

export type TruthZone = {
  label: string
  meaning: string // tooltip / aria description
  min: number // inclusive
  max: number // inclusive
  colorClass: string // Tailwind text-* class, used as currentColor on stroke + fill
}

/**
 * Default R&M-themed zone scale — 5 buckets across [0, 100].
 * Tailwind tokens are restricted to the existing palette
 * (defense-red / legal-gold / coach-green) so GH-9 can swap them
 * to portal-themed tokens without touching this component.
 */
export const DEFAULT_ZONES: readonly TruthZone[] = [
  {
    label: 'Cronenberg-Level Nonsense',
    meaning:
      'Probably mutated garbage. Do not trust it unless you enjoy lawsuits and body horror.',
    min: 0,
    max: 19,
    colorClass: 'text-defense-red',
  },
  {
    label: 'Jerry-Level Confidence',
    meaning:
      'Sounds confident. Unfortunately, so does Jerry. Needs serious verification.',
    min: 20,
    max: 39,
    colorClass: 'text-legal-gold',
  },
  {
    label: 'Aw Jeez, Maybe?',
    meaning: 'Plausible, but shaky. The Morty zone. Ask for citations.',
    min: 40,
    max: 59,
    colorClass: 'text-legal-gold',
  },
  {
    label: 'Council-Approved-ish',
    meaning:
      'Pretty solid. Still needs a quick sanity check before anyone gets smug.',
    min: 60,
    max: 79,
    colorClass: 'text-coach-green',
  },
  {
    label: 'C-137 Canon Event',
    meaning:
      'Strongly supported. Across most timelines, this holds up.',
    min: 80,
    max: 100,
    colorClass: 'text-coach-green',
  },
] as const

interface TruthOMeterProps {
  /** 0-100 score, or null for a neutral idle state. */
  score: number | null
  /** Wrapper className for caller-driven layout/sizing. */
  className?: string
  /** Needle swing duration in ms. Default 1200. */
  durationMs?: number
  /** Override the zone scale (e.g. GH-9 re-skin, GH-6 demo overrides). */
  zones?: readonly TruthZone[]
}

// Geometry — fixed viewBox so the arc renders crisply at any wrapper size.
const VIEW_W = 200
const VIEW_H = 120
const CX = 100 // center x
const CY = 100 // center y (baseline of the semicircle)
const R = 80 // arc radius
const STROKE = 14
// Arc length of a 180-degree sweep at radius R.
const ARC_LEN = Math.PI * R

// Endpoints of the 180-degree arc, drawn left-to-right across the top.
const ARC_PATH = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`

function findZone(
  score: number,
  zones: readonly TruthZone[],
): TruthZone | null {
  for (const z of zones) {
    if (score >= z.min && score <= z.max) return z
  }
  return null
}

export default function TruthOMeter({
  score,
  className,
  durationMs = 1200,
  zones = DEFAULT_ZONES,
}: TruthOMeterProps) {
  const isNull = score === null
  const safeScore = isNull ? 100 : Math.max(0, Math.min(100, score as number))

  // Score → angle. 0 → -90deg, 100 → +90deg.
  const angleDeg = safeScore * 1.8 - 90

  // Foreground arc stroke length. Null state shows zero foreground (neutral).
  const dashOffset = isNull ? ARC_LEN : ARC_LEN * (1 - safeScore / 100)

  const zone = isNull ? null : findZone(safeScore, zones)
  const zoneLabel = zone?.label ?? ''
  const zoneMeaning = zone?.meaning ?? ''
  // Null state: neutral muted color. Otherwise use the zone's Tailwind class
  // (which we drive via `currentColor` on stroke + fill).
  const colorClass = isNull ? 'text-gray-400' : (zone?.colorClass ?? 'text-gray-400')

  const ariaLabel = isNull
    ? 'Truth-O-Meter: no score yet'
    : `Truth-O-Meter: ${safeScore} out of 100, ${zoneLabel}`

  // CSS transition string shared by needle rotation and arc dashoffset.
  const transition = `transform ${durationMs}ms cubic-bezier(0.4, 0, 0.2, 1), stroke-dashoffset ${durationMs}ms cubic-bezier(0.4, 0, 0.2, 1)`

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className={`flex flex-col items-center ${className ?? ''}`}
    >
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className={`w-full max-w-xs ${colorClass}`}
        xmlns="http://www.w3.org/2000/svg"
      >
        {zoneMeaning && <title>{zoneMeaning}</title>}

        {/* Background arc — 30% opacity in current zone color. */}
        <path
          d={ARC_PATH}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKE}
          strokeLinecap="round"
          opacity={0.3}
        />

        {/* Foreground arc — length scales with score via stroke-dashoffset. */}
        <path
          d={ARC_PATH}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={ARC_LEN}
          strokeDashoffset={dashOffset}
          style={{ transition, willChange: 'stroke-dashoffset' }}
        />

        {/* Needle — rotated about the gauge center. */}
        <g
          style={{
            transform: `rotate(${angleDeg}deg)`,
            transformOrigin: `${CX}px ${CY}px`,
            transformBox: 'view-box',
            transition,
            willChange: 'transform',
          }}
        >
          <line
            x1={CX}
            y1={CY}
            x2={CX}
            y2={CY - (R - STROKE / 2 - 2)}
            stroke="currentColor"
            strokeWidth={3}
            strokeLinecap="round"
          />
          <circle cx={CX} cy={CY} r={6} fill="currentColor" />
        </g>
      </svg>

      {/* Numeric score + zone label below the arc. */}
      <div className="mt-2 flex flex-col items-center text-center">
        <div className={`text-2xl font-semibold ${colorClass}`}>
          {isNull ? '—' : safeScore}
        </div>
        {!isNull && zoneLabel && (
          <div className={`text-sm font-medium ${colorClass}`}>{zoneLabel}</div>
        )}
      </div>
    </div>
  )
}
