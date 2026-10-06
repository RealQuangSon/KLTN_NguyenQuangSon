import { useId } from "react";

/** Brand illustration; it never represents a room from the catalog. */
export function RoomIllustration({ className = "" }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      className={`room-illustration ${className}`}
      viewBox="0 0 600 460"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          id={`${id}-wall`}
          x1="60"
          y1="80"
          x2="510"
          y2="320"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#FAF3E7" />
          <stop offset="1" stopColor="#E8D9BF" />
        </linearGradient>
        <linearGradient
          id={`${id}-light`}
          x1="220"
          y1="200"
          x2="440"
          y2="360"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#FFF8DC" stopOpacity=".8" />
          <stop offset="1" stopColor="#FFF8DC" stopOpacity="0" />
        </linearGradient>
      </defs>
      <ellipse
        cx="309"
        cy="399"
        rx="228"
        ry="27"
        fill="#183E32"
        opacity=".07"
      />
      <path
        d="M80 137 305 57l216 92v197l-213 83-228-88Z"
        fill={`url(#${id}-wall)`}
      />
      <path d="m80 341 225-85 216 90-213 83Z" fill="#D2B58F" />
      <path d="m305 57 216 92v197l-216-90Z" fill="#DDD0B7" />
      <path
        d="M124 149 248 105v140l-124 46Z"
        fill="#A9C6BF"
        stroke="#FCF6E9"
        strokeWidth="12"
      />
      <path d="m148 228 18-43 19 8 25-46 30 18v73l-92 32Z" fill="#83ABA0" />
      <path d="M184 130v139m-57-50 119-44" stroke="#FCF6E9" strokeWidth="6" />
      <path d="m126 290 116-42 228 103-160 58Z" fill={`url(#${id}-light)`} />
      <path d="m244 327 68-25 117 51-70 26Z" fill="#F7EDD9" />
      <path d="m140 314 109-39 121 49-111 43Z" fill="#ECE0CC" />
      <path d="M140 314v30l118 49v-26Z" fill="#C39F77" />
      <path d="m258 367 112-43v30l-112 39Z" fill="#A78965" />
      <path d="m144 307 104-38 112 44-106 40Z" fill="#FDF9EF" />
      <path d="m142 280 72-25 42 15-72 28Z" fill="#F6EBD9" />
      <path d="m185 298 73-28 103 43-107 40-69-28Z" fill="#C97459" />
      <path d="m185 298 69 27v28l-69-28Z" fill="#A65139" />
      <path d="m165 281 47-17 22 9-47 18Z" fill="#FDF9EF" />
      <path d="m383 216 83 34v18l-83-34Z" fill="#82694B" />
      <path d="m383 216 37-14 83 34-37 14Z" fill="#AF9067" />
      <path d="M393 240v76m65-49v75" stroke="#82694B" strokeWidth="7" />
      <path d="m418 214 32 13v-23l-32-13Z" fill="#EAE6D9" />
      <path d="m418 191 18-7 32 13-18 7Z" fill="#FDF9EF" />
      <path d="m420 190 30 13v-18l-30-12Z" fill="#254D40" />
      <path d="m378 179 22 9m-12-13v34" stroke="#42634B" strokeWidth="4" />
      <path d="m373 181 15-32 21 42Z" fill="#D5AE70" />
      <path d="m376 183 26 9" stroke="#B78C52" strokeWidth="3" />
      <path
        d="m335 135 49 20v43l-49-20Z"
        fill="#F8F2E6"
        stroke="#B79C77"
        strokeWidth="5"
      />
      <path d="m345 167 13-17 17 33Z" fill="#80A391" />
      <path d="m358 168 9-8 9 23Z" fill="#BDA675" />
      <path d="m452 307 29 12-5 39-21-9Z" fill="#B97753" />
      <path d="M465 321v-70" stroke="#476B48" strokeWidth="4" />
      <path
        d="M465 281c-27-11-40-32-31-39 20 2 31 21 31 39Zm1 19c27-8 37-27 26-33-17 3-26 17-26 33Zm-1-37c-20-19-21-38-12-43 14 12 18 24 12 43Z"
        fill="#5A7E58"
      />
      <path
        d="m105 347 43 18m264-264 14 6"
        stroke="#FAF3E7"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
