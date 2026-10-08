export default function Skeletons({ n = 3, className = "grid" }) {
  return (
    <div className={className}>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skel" aria-hidden="true" />
      ))}
    </div>
  );
}
