import { Icon } from "./Shared";

export function Journey({ step = 0 }: { step?: number }) {
  const steps = [
    { title: "Chia sẻ nhu cầu", description: "Kể về nơi bạn muốn ở" },
    { title: "Xác nhận hồ sơ", description: "Bạn quyết định tiêu chí" },
    { title: "Quản lý kiểm tra", description: "Rà soát phòng & chi phí" },
    { title: "Chọn & xem phòng", description: "So sánh rồi hẹn xem" },
  ];
  return (
    <ol className="journey" aria-label="Tiến trình tìm phòng">
      {steps.map((item, index) => (
        <li
          key={item.title}
          className={
            index < step ? "complete" : index === step ? "current" : ""
          }
          aria-current={index === step ? "step" : undefined}
        >
          <span className="journey-number">
            {index < step ? <Icon name="check" size={16} /> : `0${index + 1}`}
          </span>
          <div>
            <strong>{item.title}</strong>
            <small>{item.description}</small>
          </div>
          {index !== steps.length - 1 && <Icon name="chevron" size={15} />}
        </li>
      ))}
    </ol>
  );
}
