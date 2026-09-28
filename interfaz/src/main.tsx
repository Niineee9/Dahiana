import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { conectarConDahiana } from "./estado";
import "./index.css";

conectarConDahiana();

// El menú del navegador (Atrás, Imprimir...) no pinta nada aquí; en desarrollo se deja para "Inspeccionar".
if (!import.meta.env.DEV) {
  document.addEventListener("contextmenu", (e) => e.preventDefault());
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
