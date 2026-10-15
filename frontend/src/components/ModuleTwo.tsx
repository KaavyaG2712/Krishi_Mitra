import { lazy, Suspense, useState } from "react";
import CropPlanner from "./CropPlanner";
import type { SoilResult } from "./SoilHealth";
const SoilHealth = lazy(() => import("./SoilHealth"));

export default function ModuleTwo(props: { result: SoilResult | null; onResult: (result: SoilResult) => void; onExplain: () => void }) {
  const [reportOpen, setReportOpen] = useState(false);
  return <><CropPlanner /><details className="panel mt-3" onToggle={e => setReportOpen(e.currentTarget.open)}>
    <summary className="font-bold">Optional: use an actual soil test or saved report</summary>
    <p className="help mt-3">You can view and discuss a laboratory report separately. The crop comparison above uses mapped area data; it does not silently replace it with report values.</p>
    {reportOpen && <Suspense fallback={<p>Loading report tools…</p>}><SoilHealth {...props} /></Suspense>}
  </details></>;
}
