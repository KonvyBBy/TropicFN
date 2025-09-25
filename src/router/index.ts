
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { useRoutes } from "react-router-dom";
import { useEffect } from "react";
import routes from "./config";

let navigateResolver: (navigate: ReturnType<typeof useNavigate>) => void;

declare global {
  interface Window {
    REACT_APP_NAVIGATE: ReturnType<typeof useNavigate>;
  }
}

export const navigatePromise = new Promise<NavigateFunction>((resolve) => {
  navigateResolver = resolve;
});

export function AppRoutes() {
  const navigate = useNavigate();
  const element = useRoutes(routes);
  
  useEffect(() => {
    if (!window.REACT_APP_NAVIGATE) {
      window.REACT_APP_NAVIGATE = navigate;
      navigateResolver(navigate);
    }
  }, [navigate]);
  
  return element;
}
