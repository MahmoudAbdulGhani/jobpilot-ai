export function JobDescription({ text }: { text: string | null }) {
  if (!text) return <p className="muted">No description saved.</p>;
  return <>{text.split(/\n\s*\n/).map((block, index) => {
    const lines = block.split('\n').map(line => line.trim()).filter(Boolean);
    const bullets = lines.slice(1).filter(line => /^[•*-]\s*/.test(line));
    if (lines.length > 1 && bullets.length === lines.length - 1) return <section className="description-block" key={index}><h2>{lines[0]}</h2><ul>{bullets.map((line, item) => <li key={item}>{line.replace(/^[•*-]\s*/, '')}</li>)}</ul></section>;
    return <p className="preserve-lines" key={index}>{block}</p>;
  })}</>;
}
