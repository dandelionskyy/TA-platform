export default function SkeletonLoader() {
  return (
    <div className="chat-box">
      <div className="message bot" style={{ maxWidth: '90%' }}>
        <div className="skeleton skeleton-avatar" />
        <div style={{ flex: 1 }}>
          <div className="skeleton skeleton-text" />
          <div className="skeleton skeleton-text" />
        </div>
      </div>
      <div className="message user" style={{ maxWidth: '60%', marginLeft: 'auto' }}>
        <div style={{ width: '100%' }}>
          <div className="skeleton skeleton-text" />
        </div>
      </div>
      <div className="message bot" style={{ maxWidth: '90%' }}>
        <div className="skeleton skeleton-avatar" />
        <div style={{ flex: 1 }}>
          <div className="skeleton skeleton-text" />
          <div className="skeleton skeleton-text" />
          <div className="skeleton skeleton-text" />
        </div>
      </div>
    </div>
  );
}
