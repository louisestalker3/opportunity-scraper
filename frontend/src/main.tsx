import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import App from "./App";
import Dashboard from "./pages/Dashboard";
import OpportunityDetail from "./pages/OpportunityDetail";
import Pipeline from "./pages/Pipeline";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import CloneAnalysis from "./pages/CloneAnalysis";
import Settings from "./pages/Settings";

import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 2,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "opportunity/:id", element: <OpportunityDetail /> },
      { path: "pipeline", element: <Pipeline /> },
      { path: "projects", element: <Projects /> },
      { path: "project/:id", element: <ProjectDetail /> },
      { path: "analyze", element: <CloneAnalysis /> },
      { path: "settings", element: <Settings /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
);
