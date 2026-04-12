interface SkeletonProps {
  width?: string;
  height?: string;
  borderRadius?: string;
  count?: number;
  gap?: string;
}

export function Skeleton({
  width = '100%',
  height = '14px',
  borderRadius = 'var(--radius-sm)',
  count = 1,
  gap = '8px',
}: SkeletonProps) {
  if (count === 1) {
    return <div style={{ ...styles.skeleton, width, height, borderRadius }} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ ...styles.skeleton, width, height, borderRadius }} />
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  skeleton: {
    background: 'linear-gradient(90deg, var(--bg-hover) 25%, var(--border-light) 50%, var(--bg-hover) 75%)',
    backgroundSize: '200% 100%',
    animation: 'shimmer 1.5s ease-in-out infinite',
  },
};
