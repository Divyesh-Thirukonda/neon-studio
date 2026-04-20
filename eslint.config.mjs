import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  { ignores: [".next/**", "node_modules/**", "exports/**", "midi/**", "daw/**"] },
  ...nextVitals,
  ...nextTypescript
];

export default eslintConfig;
