import { Component, ReactNode } from "react";

/** Keep a stale deployment chunk or render failure from becoming a blank page. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="panel m-6" role="alert">
      <h1 className="text-2xl font-bold">This screen could not load</h1>
      <p className="help">Check your connection and reload the app. Unsaved entries on this screen will be cleared.</p>
      <button type="button" className="primary mt-4" onClick={() => window.location.reload()}>Reload app</button>
    </main>;
    return this.props.children;
  }
}
