import { Icon } from "./Shared";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Icon name="home" size={22} />
      </span>
      <span className="brand-name">
        <span className="brand-title">
          HomeMatch<span className="brand-period">.</span>
        </span>
        <small className="brand-tag">Trợ lý tìm phòng</small>
      </span>
    </div>
  );
}
