import { useApp } from '../store'
import { extractDraftOnly } from '../lib/extract'

export default function Answers() {
  const answers = useApp(s => s.answers)
  const pick = useApp(s => s.pickAnswer)

  const useAsDoc = async (a: any) => {
    const draft = extractDraftOnly(a.text)
    await pick({ ...a, text: draft }, 'replace') // only chosen draft moves to editor
  }

  return (
    <div>
      <div className="section-title">Answers (3 AIs)</div>
      {answers.length === 0 && <div className="mini">Ask a question to see 3 drafts.</div>}
      {answers.map((a) => {
        const draft = extractDraftOnly(a.text)
        return (
          <div key={a.id} className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>{a.provider.toUpperCase()}</strong>
              <span className="mini">{a.latencyMs ? `${a.latencyMs} ms` : ''}</span>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{draft}</pre>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => useAsDoc(a)}>Use as Document (Replace)</button>
              <button className="btn" onClick={() => pick({ ...a, text: draft }, 'append')}>Append Draft</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
