import { FormEvent, useEffect, useState } from "react";

type Citation = {
  source: string;
  source_url: string;
  series_id: string;
  observation_date: string;
  calculation_id?: string | null;
};

type Claim = { claim_id: string; text: string; citations: Citation[] };
type Section = { heading: string; claims: Claim[] };
type Report = {
  title: string;
  as_of: string;
  sections: Section[];
  metadata: { disclaimer?: string };
};
type AskResponse = { answer: string; evidence: Citation[]; mode: string };

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

function Evidence({ citations }: { citations: Citation[] }) {
  return (
    <div className="evidence">
      {citations.map((citation, index) => (
        <a
          className="evidence-chip"
          href={citation.source_url}
          target="_blank"
          rel="noreferrer"
          key={`${citation.series_id}-${citation.observation_date}-${index}`}
        >
          {citation.series_id} · {citation.observation_date}
        </a>
      ))}
    </div>
  );
}

export default function App() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string>("");
  const [question, setQuestion] = useState("Explain Midwest diesel tightness this week");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/reports/weekly`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json()).detail ?? "Report unavailable");
        return response.json();
      })
      .then(setReport)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  async function ask(event: FormEvent) {
    event.preventDefault();
    setAsking(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!response.ok) throw new Error((await response.json()).detail ?? "Question failed");
      setAnswer(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Question failed");
    } finally {
      setAsking(false);
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <span className="eyebrow">EVIDENCE-FIRST PETROLEUM INTELLIGENCE</span>
          <h1>OilSignal</h1>
          <p>Operational oil-market briefs where every number has a dataset, date, and calculation trail.</p>
        </div>
        <span className="status">LOCAL · AUDITABLE</span>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">LATEST BRIEF</span>
            <h2>{report?.title ?? "Waiting for ingested data"}</h2>
          </div>
          {report && <span className="asof">AS OF {report.as_of}</span>}
        </div>
        <div className="grid">
          {report?.sections.map((section) => (
            <article className="card" key={section.heading}>
              <h3>{section.heading}</h3>
              {section.claims.map((claim) => (
                <div key={claim.claim_id}>
                  <p>{claim.text}</p>
                  <Evidence citations={claim.citations} />
                </div>
              ))}
            </article>
          ))}
        </div>
      </section>

      <section className="panel ask-panel">
        <div>
          <span className="eyebrow">ASK THE FUNDAMENTALS</span>
          <h2>Explain what changed</h2>
          <p className="muted">The default path is deterministic and only answers from ingested observations.</p>
        </div>
        <form onSubmit={ask}>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          <button disabled={asking || question.trim().length < 3}>{asking ? "Checking…" : "Explain with evidence"}</button>
        </form>
        {answer && (
          <div className="answer">
            <p>{answer.answer}</p>
            <Evidence citations={answer.evidence} />
          </div>
        )}
      </section>

      <footer>{report?.metadata.disclaimer ?? "Decision support only; not trading or investment advice."}</footer>
    </main>
  );
}
