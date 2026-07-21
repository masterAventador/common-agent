import { ReactFlowProvider } from "@xyflow/react";

import { WorkflowCanvas } from "./WorkflowCanvas";
import type { WorkflowEditorAction, WorkflowEditorState } from "./workflowEditor";
import type { WorkflowRun } from "../../api/workflowRuns";
import type { Dispatch } from "react";

export function WorkflowCanvasSurface({
  state,
  run,
  editingLocked,
  dispatch,
}: {
  state: WorkflowEditorState;
  run: WorkflowRun | undefined;
  editingLocked: boolean;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvas
        state={state}
        run={run}
        editingLocked={editingLocked}
        dispatch={dispatch}
      />
    </ReactFlowProvider>
  );
}
