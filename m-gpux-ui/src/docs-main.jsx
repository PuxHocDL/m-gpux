import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import DocsApp from "./DocsApp.jsx";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <DocsApp />
  </StrictMode>
);
