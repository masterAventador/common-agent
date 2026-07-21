import { useId } from "react";

const WAVE_PATH = "M9 25 L15.5 25 L20 13.5 L24 27 L27.5 21 L31 21";

export function BrandLogo({ size = 36 }: { size?: number }) {
  const gradientId = `common-agent-logo-${useId().replaceAll(":", "")}`;
  return (
    <svg
      aria-hidden="true"
      data-testid="brand-logo"
      className="brand-logo-svg"
      viewBox="0 0 40 40"
      width={size}
      height={size}
    >
      <defs>
        <linearGradient
          id={gradientId}
          gradientUnits="userSpaceOnUse"
          x1="-8"
          y1="0"
          x2="8"
          y2="0"
        >
          <stop offset="0" stopColor="#4DA3FF" stopOpacity="0" />
          <stop offset=".42" stopColor="#4DA3FF" stopOpacity="1" />
          <stop offset=".5" stopColor="#EAF4FF" stopOpacity="1" />
          <stop offset=".58" stopColor="#4DA3FF" stopOpacity="1" />
          <stop offset="1" stopColor="#4DA3FF" stopOpacity="0" />
          <animateTransform
            attributeName="gradientTransform"
            type="translate"
            from="0 0"
            to="47 0"
            dur="2s"
            calcMode="spline"
            keyTimes="0;1"
            keySplines="0.42 0 0.58 1"
            repeatCount="indefinite"
          />
        </linearGradient>
      </defs>
      <g transform="translate(20 20) scale(1.3) translate(-20 -20)">
        <path
          d={WAVE_PATH}
          fill="none"
          stroke="rgba(250, 250, 250, 0.28)"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          className="brand-logo-scan"
          d={WAVE_PATH}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}
