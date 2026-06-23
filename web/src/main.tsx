import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Docs from "./Docs";
import "./index.css";

// Tiny path router — nginx serves index.html for any path (SPA fallback), so /docs and
// /docs/<slug> load here and we pick the view. Everything else is the dashboard.
const isDocs =
  window.location.pathname === "/docs" || window.location.pathname.startsWith("/docs/");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isDocs ? <Docs /> : <App />}</React.StrictMode>
);
