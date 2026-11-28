import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.css";
import { RemoteRecorder } from "./RemoteRecorder";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RemoteRecorder />
  </StrictMode>,
);
