// Displays the ArchLens evaluation suite's last-measured results
// (tests/test_evaluation.py, run against the synthetic + real public
// corpus). These are the actual printed values from that test run, not
// live-computed here — the dashboard doesn't re-run the backend
// evaluation suite on every page view, so the numbers are labeled as a
// historical snapshot, per CLAUDE.md rule 3 (don't fabricate results:
// showing a number as "live" when it isn't would misrepresent it).
const MEASURED_AT = 'last verified backend test run (see README.md "Evaluation" section for the full pytest output)'

const RETRIEVAL_METRICS = [
  { label: 'Recall@5', value: '1.00' },
  { label: 'Recall@10', value: '1.00' },
  { label: 'MRR', value: '1.00' },
  { label: 'nDCG@5', value: '1.00' },
]

const BASELINE_COMPARISON = [
  { label: 'Baseline (lexical-only) Recall@5', value: '0.125' },
  { label: 'ArchLens (hybrid + rerank) Recall@5', value: '1.00' },
]

const REVIEW_METRICS = [
  { label: 'Finding correctness', value: '1.00' },
  { label: 'Finding completeness', value: '1.00' },
  { label: 'Citation accuracy', value: '34/34 verified against real Postgres rows' },
  { label: 'Groundedness (mean)', value: '1.00' },
  { label: 'False-confidence rate', value: '0.00' },
]

const LATENCY_METRICS = [
  { label: '/review latency (template provider)', value: '≈0.15s' },
  { label: '/answer latency (template provider)', value: '≈1.5s' },
]

function MetricTable({ title, rows }: { title: string; rows: { label: string; value: string }[] }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <table>
        <caption className="visually-hidden">{title}</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">Value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td>{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const HAS_RESULTS =
  RETRIEVAL_METRICS.length > 0 ||
  BASELINE_COMPARISON.length > 0 ||
  REVIEW_METRICS.length > 0 ||
  LATENCY_METRICS.length > 0

export function EvaluationView() {
  return (
    <section id="evaluation" aria-labelledby="eval-heading" className="page-section">
      <h2 id="eval-heading">Evaluation</h2>
      <p className="section-description">
        Measure how well ArchLens retrieves evidence and produces accurate architecture review
        results.
      </p>
      <p className="status-text">
        Snapshot from the {MEASURED_AT}. Re-run <code>pytest tests/test_evaluation.py -s</code> against a running
        backend to reproduce these numbers on your own machine.
      </p>
      {!HAS_RESULTS && <p className="status-text">No evaluation results available yet.</p>}
      {HAS_RESULTS && (
        <>
          <MetricTable title="Retrieval (golden cases: synthetic + public corpus)" rows={RETRIEVAL_METRICS} />
          <MetricTable title="Baseline vs ArchLens" rows={BASELINE_COMPARISON} />
          <MetricTable title="Review / findings" rows={REVIEW_METRICS} />
          <MetricTable title="Latency (local, template provider, no external LLM)" rows={LATENCY_METRICS} />
        </>
      )}
    </section>
  )
}
