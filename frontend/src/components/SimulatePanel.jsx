import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { SeverityBadge, SEVERITY_TEXT, levelFor } from './ui.jsx'

const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const SCENARIOS = [
  {
    id: 'iam_breach',
    title: 'IAM Breach',
    desc: 'a stolen role signs in from a new region and launches compute.',
  },
  {
    id: 'bot_traffic',
    title: 'Bot Traffic',
    desc: 'scrapers flood public endpoints and push up CPU and spend.',
  },
  {
    id: 'resource_waste',
    title: 'Resource Waste',
    desc: 'idle instances and unattached volumes drain the budget.',
  },
]

const MOCK_RESULTS = {
  iam_breach: {
    score: 94,
    severity: 'CRITICAL',
    title: 'Possible compromised credentials: unusual IAM login followed by new EC2 instances',
    summary:
      'An IAM role was assumed from an unfamiliar IP in eu-west-1, followed by rapid compute provisioning and broad security group exposure.',
    findings: [
      'IAM role assumed from an unfamiliar IP in eu-west-1',
      '8 EC2 instances launched in a region with no prior activity',
      'Security group opened to 0.0.0.0/0',
      'Daily spend projected at $92 against $8 expected',
    ],
    actions: [
      "Disable the role's keys and revoke sessions",
      'Stop the new instances and keep them for forensics',
      'Remove the 0.0.0.0/0 rule',
    ],
    footnote: 'Local preview. Nothing was sent to the backend.',
  },
  bot_traffic: {
    score: 78,
    severity: 'HIGH',
    title: 'Automated bot traffic on /api/products driving CPU and cost up',
    summary:
      'Automated scraping activity is generating heavy request surges against public product endpoints, triggering compute scaling and increased spend.',
    findings: [
      'Requests per hour rose from about 5K to 480K',
      '91% of requests come from 3 IP ranges with the same user agent',
      'web-api-01 CPU passed 85% and auto scaling added capacity',
      'About $318 of extra spend today',
    ],
    actions: [
      'WAF rate limit',
      'Edge caching',
      'Cap auto scaling',
    ],
    footnote: 'Local preview. Nothing was sent to the backend.',
  },
  resource_waste: {
    score: 41,
    severity: 'MEDIUM',
    title: 'Idle and unattached resources are costing about $422 a month',
    summary:
      'Several compute and storage resources have been identified with prolonged low utilization or unattached states contributing to avoidable spend.',
    findings: [
      'batch-worker-02 has averaged 7% CPU for 14 days',
      '2 unattached EBS volumes with no snapshot ($55 a month)',
      'Cold logs sit in S3 Standard ($305 a month)',
    ],
    actions: [
      'Downsize',
      'Snapshot then delete volumes',
      'Lifecycle rule to Glacier',
    ],
    footnote: 'Local preview. Nothing was sent to the backend.',
  },
}

function parseSimulationResponse(body) {
  if (!body) return { empty: true }
  const root = body.data ?? body

  const incident =
    root.incident ??
    root.correlated_incident ??
    root.alert ??
    (Array.isArray(root.incidents) ? root.incidents[0] : null) ??
    root

  let score = null
  if (incident && incident.risk_score != null) {
    const num = Number(incident.risk_score)
    if (!Number.isNaN(num)) {
      score = Math.round(num)
    }
  }

  let severity = null
  if (incident && incident.severity) {
    severity = String(incident.severity).toUpperCase()
  } else if (score != null) {
    severity = levelFor(score)
  }

  const title = incident?.title || null
  const summary = incident?.summary || null

  let rawFindings = root.findings ?? root.audit_findings ?? incident?.findings
  if (!rawFindings) {
    const signals = root.signals ?? incident?.signals
    if (Array.isArray(signals)) {
      rawFindings = signals
    } else if (signals && typeof signals === 'object') {
      rawFindings = Object.values(signals).flat()
    }
  }

  const findings = []
  if (Array.isArray(rawFindings)) {
    for (const item of rawFindings) {
      if (typeof item === 'string') {
        findings.push(item)
      } else if (item && typeof item === 'object') {
        const text = item.message ?? item.summary ?? item.description ?? item.title
        if (text) findings.push(String(text))
      }
    }
  }

  const rawActions = []
  if (Array.isArray(incident?.recommended_actions)) {
    rawActions.push(...incident.recommended_actions)
  }
  const recs = root.recommendations ?? incident?.recommendations
  if (Array.isArray(recs)) {
    for (const r of recs) {
      if (typeof r === 'string') {
        rawActions.push(r)
      } else if (r && typeof r === 'object') {
        const act = r.action ?? r.title
        if (act) rawActions.push(String(act))
      }
    }
  }
  const actions = rawActions
    .map((a) => (typeof a === 'string' ? a : (a?.action ?? a?.title ?? a?.text ?? JSON.stringify(a))))
    .filter(Boolean)

  const isUsable = title || summary || score != null || findings.length > 0 || actions.length > 0
  if (!isUsable) return { empty: true }

  return {
    score,
    severity: severity || (score != null ? levelFor(score) : 'LOW'),
    title,
    summary,
    findings,
    actions,
    footnote: 'Result from the backend simulation.',
  }
}

export default function SimulatePanel({ open, onClose, onSimulated }) {
  const [scenario, setScenario] = useState('iam_breach')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const dialogRef = useRef(null)
  const triggerRef = useRef(null)
  const abortRef = useRef(null)

  // Reset state and manage focus/scroll whenever opened
  useEffect(() => {
    if (open) {
      setScenario('iam_breach')
      setResult(null)
      setError(null)
      setLoading(false)

      triggerRef.current = document.activeElement
      dialogRef.current?.focus()

      const prevOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'

      return () => {
        document.body.style.overflow = prevOverflow
        if (triggerRef.current && typeof triggerRef.current.focus === 'function') {
          triggerRef.current.focus()
        }
      }
    }
  }, [open])

  // Abort ongoing fetch on unmount or close
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  // Keyboard navigation: Escape to close and Tab trapping
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        handleClose()
        return
      }

      if (e.key === 'Tab') {
        const container = dialogRef.current
        if (!container) return
        const focusable = Array.from(
          container.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        ).filter((el) => el.offsetParent !== null || el.getClientRects().length > 0)

        if (focusable.length === 0) {
          e.preventDefault()
          return
        }

        const first = focusable[0]
        const last = focusable[focusable.length - 1]

        if (e.shiftKey) {
          if (document.activeElement === first || document.activeElement === container) {
            e.preventDefault()
            last.focus()
          }
        } else {
          if (document.activeElement === last || document.activeElement === container) {
            e.preventDefault()
            first.focus()
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const handleClose = () => {
    abortRef.current?.abort()
    onClose()
  }

  const handleScenarioChange = (e) => {
    setScenario(e.target.value)
    setResult(null)
    setError(null)
  }

  const handleRunSimulation = async () => {
    if (USE_MOCK) {
      setError(null)
      setResult(MOCK_RESULTS[scenario] || null)
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch(`${BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario }),
        signal: controller.signal,
      })

      if (!res.ok) {
        throw new Error(`Simulation request failed (${res.status})`)
      }

      const body = await res.json()
      const parsed = parseSimulationResponse(body)
      setResult(parsed)
      onSimulated?.()
    } catch (err) {
      if (err.name === 'AbortError') return
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 transition-opacity"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="simulate-panel-title"
        tabIndex="-1"
        className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-line bg-panel text-text shadow-2xl focus:outline-none"
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 id="simulate-panel-title" className="text-base font-semibold text-text">
            Simulate an incident
          </h2>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close"
            className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-text transition-colors"
          >
            <X size={20} aria-hidden />
          </button>
        </header>

        {/* Content area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Radio group */}
          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold text-text">Scenario</legend>
            <div className="space-y-2">
              {SCENARIOS.map((s) => (
                <label
                  key={s.id}
                  htmlFor={s.id}
                  className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                    scenario === s.id
                      ? 'border-accent bg-raised'
                      : 'border-line bg-panel hover:bg-raised/50'
                  } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <input
                    type="radio"
                    id={s.id}
                    name="scenario"
                    value={s.id}
                    checked={scenario === s.id}
                    disabled={loading}
                    onChange={handleScenarioChange}
                    className="mt-1 shrink-0 accent-accent"
                  />
                  <div className="text-sm">
                    <p className="font-medium text-text">{s.title}</p>
                    <p className="mt-0.5 text-xs text-muted">{s.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </fieldset>

          {/* Action button */}
          <button
            type="button"
            disabled={loading}
            onClick={handleRunSimulation}
            className="w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Running simulation…' : 'Run simulation'}
          </button>

          {/* Results area */}
          <div aria-live="polite" className="space-y-5">
            {error && (
              <div className="rounded-lg border border-crit/30 bg-crit/10 p-5 text-sm" role="alert">
                <p className="font-medium text-crit">Simulation failed</p>
                <p className="mt-1 text-muted">{error.message || String(error)}</p>
                <p className="mt-2 text-xs text-muted">
                  Check that the backend is running at {BASE} and exposes POST /simulate.
                </p>
              </div>
            )}

            {result &&
              (result.empty ? (
                <div className="rounded-lg border border-line bg-raised/30 p-4 text-sm text-muted">
                  The backend responded but returned no incident details for this scenario.
                </div>
              ) : (
                <div className="space-y-5 rounded-lg border border-line bg-raised/30 p-5">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-muted">Risk score</p>
                    <div className="mt-1 flex items-center gap-3">
                      <span
                        className={`text-5xl font-semibold ${
                          result.score != null ? SEVERITY_TEXT[result.severity] : 'text-muted'
                        }`}
                      >
                        {result.score != null ? result.score : '—'}
                      </span>
                      {result.severity && <SeverityBadge level={result.severity} />}
                    </div>
                  </div>

                  {result.title && (
                    <h3 className="text-base font-semibold leading-snug text-text">
                      {result.title}
                    </h3>
                  )}

                  {result.summary && (
                    <p className="text-sm leading-relaxed text-text/90">{result.summary}</p>
                  )}

                  {result.findings?.length > 0 && (
                    <div className="space-y-1.5">
                      <h4 className="text-sm font-semibold text-text">Findings</h4>
                      <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
                        {result.findings.map((f, i) => (
                          <li key={i}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {result.actions?.length > 0 && (
                    <div className="space-y-1.5">
                      <h4 className="text-sm font-semibold text-text">What to do</h4>
                      <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-text">
                        {result.actions.map((act, i) => (
                          <li key={i}>{act}</li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {result.footnote && (
                    <p className="border-t border-line/60 pt-3 text-xs text-muted">
                      {result.footnote}
                    </p>
                  )}
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  )
}
