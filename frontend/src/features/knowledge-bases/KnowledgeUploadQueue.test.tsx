import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KnowledgeUploadQueue } from "./KnowledgeUploadQueue";

const knowledgeApi = vi.hoisted(() => ({
  retryKnowledgeDocument: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
}));

vi.mock("../../api/knowledge", () => knowledgeApi);

const parsingDocument = (id: string, name: string) => ({
  id,
  knowledge_base_id: "kb-1",
  name,
  size_bytes: 7,
  parsing_status: "parsing" as const,
  error_code: null,
});

function deferred<Result>() {
  let resolve!: (value: Result) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Result>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("KnowledgeUploadQueue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    knowledgeApi.retryKnowledgeDocument.mockResolvedValue(
      parsingDocument("doc-retried", "retry.txt"),
    );
  });

  it("accepts multiple files and never uploads more than two concurrently", async () => {
    const first = deferred<ReturnType<typeof parsingDocument>>();
    const second = deferred<ReturnType<typeof parsingDocument>>();
    const third = deferred<ReturnType<typeof parsingDocument>>();
    knowledgeApi.uploadKnowledgeDocument
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
      .mockReturnValueOnce(third.promise);
    const changed = vi.fn();
    const user = userEvent.setup();
    render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[]}
        onDocumentsChanged={changed}
      />,
    );
    const files = ["one.txt", "two.md", "three.txt"].map(
      (name) => new File(["content"], name, { type: "text/plain" }),
    );

    await user.upload(screen.getByLabelText("选择或拖拽文档"), files);
    expect(screen.getAllByText("等待上传")).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "开始上传" }));

    await waitFor(() => expect(knowledgeApi.uploadKnowledgeDocument).toHaveBeenCalledTimes(2));
    expect(knowledgeApi.uploadKnowledgeDocument.mock.calls[0]).toEqual(["kb-1", files[0]]);
    expect(knowledgeApi.uploadKnowledgeDocument.mock.calls[1]).toEqual(["kb-1", files[1]]);
    first.resolve(parsingDocument("doc-1", "one.txt"));
    await waitFor(() => expect(knowledgeApi.uploadKnowledgeDocument).toHaveBeenCalledTimes(3));
    expect(knowledgeApi.uploadKnowledgeDocument.mock.calls[2]).toEqual(["kb-1", files[2]]);
    second.resolve(parsingDocument("doc-2", "two.md"));
    third.resolve(parsingDocument("doc-3", "three.txt"));
    await waitFor(() => expect(screen.getAllByText("解析中")).toHaveLength(3));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  });

  it("snapshots the browser FileList before resetting the file input", async () => {
    render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[]}
        onDocumentsChanged={vi.fn()}
      />,
    );
    const input = screen.getByLabelText("选择或拖拽文档") as HTMLInputElement;
    const selected = [new File(["content"], "selected.txt", { type: "text/plain" })];
    Object.defineProperty(input, "files", {
      configurable: true,
      get: () => selected,
    });
    Object.defineProperty(input, "value", {
      configurable: true,
      get: () => "",
      set: () => {
        selected.length = 0;
      },
    });

    fireEvent.change(input);

    expect(await screen.findByText("selected.txt")).toBeInTheDocument();
  });

  it("does not report a successful upload as failed when the list refresh fails", async () => {
    knowledgeApi.uploadKnowledgeDocument.mockResolvedValueOnce(
      parsingDocument("doc-uploaded", "uploaded.txt"),
    );
    const user = userEvent.setup();
    render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[]}
        onDocumentsChanged={vi.fn().mockRejectedValue(new Error("列表刷新失败"))}
      />,
    );

    await user.upload(
      screen.getByLabelText("选择或拖拽文档"),
      new File(["content"], "uploaded.txt", { type: "text/plain" }),
    );
    await user.click(screen.getByRole("button", { name: "开始上传" }));

    expect(await screen.findByText("解析中")).toBeInTheDocument();
    expect(screen.queryByText("列表刷新失败")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试 uploaded.txt" })).not.toBeInTheDocument();
  });

  it("supports drag and drop while rejecting unsupported, oversized and duplicate files", async () => {
    const existing = parsingDocument("doc-existing", "existing.txt");
    render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[existing]}
        onDocumentsChanged={vi.fn()}
      />,
    );
    const accepted = new File(["valid"], "accepted.md", { type: "text/markdown" });
    const unsupported = new File(["bad"], "payload.exe", {
      type: "application/octet-stream",
    });
    const oversized = new File([new Uint8Array(20 * 1024 * 1024 + 1)], "huge.pdf", {
      type: "application/pdf",
    });
    const empty = new File([], "empty.txt", { type: "text/plain" });
    const duplicate = new File(["content"], "existing.txt", { type: "text/plain" });
    const queuedDuplicate = new File(["valid"], "accepted.md", {
      type: "text/markdown",
      lastModified: accepted.lastModified + 1,
    });

    fireEvent.drop(screen.getByRole("button", { name: "拖拽上传区域" }), {
      dataTransfer: {
        files: [accepted, unsupported, oversized, empty, duplicate, queuedDuplicate],
      },
    });

    expect(await screen.findByText("accepted.md")).toBeInTheDocument();
    expect(screen.getByText(/payload\.exe.*不支持的文件类型/)).toBeInTheDocument();
    expect(screen.getByText(/huge\.pdf.*超过 20 MiB/)).toBeInTheDocument();
    expect(screen.getByText(/empty\.txt.*文档内容不能为空/)).toBeInTheDocument();
    expect(screen.getByText(/existing\.txt.*已存在或已在队列中/)).toBeInTheDocument();
    expect(screen.getByText(/accepted\.md.*已存在或已在队列中/)).toBeInTheDocument();
  });

  it("limits one upload queue to twenty files", async () => {
    render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[]}
        onDocumentsChanged={vi.fn()}
      />,
    );
    const files = Array.from(
      { length: 21 },
      (_, index) => new File([`content-${index}`], `document-${index}.txt`, { type: "text/plain" }),
    );

    fireEvent.drop(screen.getByRole("button", { name: "拖拽上传区域" }), {
      dataTransfer: { files },
    });

    expect(await screen.findAllByText("等待上传")).toHaveLength(20);
    expect(screen.getByText(/document-20\.txt.*一次最多加入 20 份文档/)).toBeInTheDocument();
  });

  it("keeps successful items and retries only the failed item", async () => {
    knowledgeApi.uploadKnowledgeDocument
      .mockResolvedValueOnce(parsingDocument("doc-success", "success.txt"))
      .mockRejectedValueOnce(new Error("上游暂时不可用"))
      .mockResolvedValueOnce(parsingDocument("doc-retried", "retry.txt"));
    const changed = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[]}
        onDocumentsChanged={changed}
      />,
    );
    const files = [
      new File(["success"], "success.txt", { type: "text/plain" }),
      new File(["retry"], "retry.txt", { type: "text/plain" }),
    ];

    await user.upload(screen.getByLabelText("选择或拖拽文档"), files);
    await user.click(screen.getByRole("button", { name: "开始上传" }));
    expect(await screen.findByText("上游暂时不可用")).toBeInTheDocument();
    expect(screen.getByText("解析中")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试 retry.txt" }));
    await waitFor(() => expect(knowledgeApi.uploadKnowledgeDocument).toHaveBeenCalledTimes(3));
    expect(knowledgeApi.uploadKnowledgeDocument.mock.calls[2]?.[1]).toBe(files[1]);

    rerender(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[
          { ...parsingDocument("doc-success", "success.txt"), parsing_status: "completed" },
          { ...parsingDocument("doc-retried", "retry.txt"), parsing_status: "failed", error_code: "parser_failed" },
        ]}
        onDocumentsChanged={changed}
      />,
    );
    expect(await screen.findByText("已完成")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试 retry.txt" }));
    await waitFor(() =>
      expect(knowledgeApi.retryKnowledgeDocument).toHaveBeenCalledWith("kb-1", "doc-retried"),
    );
    expect(knowledgeApi.uploadKnowledgeDocument).toHaveBeenCalledTimes(3);
  });

  it("shows a terminal failure when a refreshed retry fails again immediately", async () => {
    const retryRefresh = deferred<void>();
    const changed = vi
      .fn<() => void | Promise<void>>()
      .mockResolvedValueOnce(undefined)
      .mockReturnValueOnce(retryRefresh.promise);
    knowledgeApi.uploadKnowledgeDocument.mockResolvedValueOnce(
      parsingDocument("doc-fast-failure", "fast-failure.txt"),
    );
    knowledgeApi.retryKnowledgeDocument.mockResolvedValueOnce(
      parsingDocument("doc-fast-failure", "fast-failure.txt"),
    );
    const user = userEvent.setup();
    const { rerender } = render(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[]}
        onDocumentsChanged={changed}
      />,
    );

    await user.upload(
      screen.getByLabelText("选择或拖拽文档"),
      new File(["content"], "fast-failure.txt", { type: "text/plain" }),
    );
    await user.click(screen.getByRole("button", { name: "开始上传" }));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    const failedDocument = {
      ...parsingDocument("doc-fast-failure", "fast-failure.txt"),
      parsing_status: "failed" as const,
      error_code: "document_parsing_failed",
    };
    rerender(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[failedDocument]}
        onDocumentsChanged={changed}
      />,
    );
    await user.click(screen.getByRole("button", { name: "重试 fast-failure.txt" }));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(2));
    expect(screen.getByText("解析中")).toBeInTheDocument();

    rerender(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[{ ...failedDocument }]}
        onDocumentsChanged={changed}
      />,
    );
    retryRefresh.resolve();
    rerender(
      <KnowledgeUploadQueue
        knowledgeBaseId="kb-1"
        documents={[{ ...failedDocument }]}
        onDocumentsChanged={changed}
      />,
    );

    expect(await screen.findByText("失败")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试 fast-failure.txt" })).toBeEnabled();
  });
});
