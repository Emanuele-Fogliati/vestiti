import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AppProvider } from "./lib/app-context";
import "./theme/tokens.css";
import "./theme/structure.css";
import "./theme/app.css";
import "./theme/board.css";
import "./theme/start.css";
import "./theme/calm.css";
import "./theme/tabs.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </StrictMode>,
);
