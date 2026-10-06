import { Icon } from "./Shared";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Icon name="home" size={22} />
      </span>
      <span className="brand-name">
        HomeMatch<span className="brand-period">.</span>
      </span>
    </div>
  );
}
