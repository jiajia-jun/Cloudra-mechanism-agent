import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 2_000, retry: 1, refetchOnWindowFocus: false }
  }
});

class ErrorBoundary extends React.Component<React.PropsWithChildren, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Cloudra UI render error", error, info);
  }

  render() {
    if (this.state.error) {
      return <main className="fatal-error">
        <div className="fatal-code">UI / ERROR</div>
        <h1>界面遇到了一条无法显示的数据</h1>
        <pre>{this.state.error.message}</pre>
        <button onClick={() => location.reload()}>刷新界面</button>
      </main>;
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary><App /></ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>
);
