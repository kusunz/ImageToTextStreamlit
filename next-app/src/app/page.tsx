"use client";

import { useEffect, useState } from "react";
import { ExtractedRow } from "@/types/schema";
import {
  Upload,
  FileText,
  Save,
  Download,
  Search,
  CheckCircle2,
  AlertTriangle,
  RotateCw,
  Database,
  Layers,
  Sparkles,
} from "lucide-react";

interface ModelOption {
  name: string;
  displayName: string;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<"extract" | "data">("extract");
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("gemini-3.5-flash-lite");
  const [reviewModel, setReviewModel] = useState<string>("gemma-4-26b");
  const [temperature, setTemperature] = useState<number>(0.0);

  // Upload & Extraction state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [extractedRows, setExtractedRows] = useState<ExtractedRow[]>([]);
  const [rawExtractions, setRawExtractions] = useState<unknown[]>([]);
  const [extractionErrors, setExtractionErrors] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Metrics
  const [metrics, setMetrics] = useState<{
    reread_count: number;
    needs_review_count: number;
  } | null>(null);

  // Data Explorer state
  const [dbRows, setDbRows] = useState<ExtractedRow[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [totalCount, setTotalCount] = useState<number>(0);
  const [queryLatency, setQueryLatency] = useState<number>(0);
  const [isLoadingDb, setIsLoadingDb] = useState<boolean>(false);

  useEffect(() => {
    fetch("/api/models")
      .then((res) => res.json())
      .then((data) => {
        if (data.models && data.models.length > 0) {
          setModels(data.models);
          const hasPrimary = data.models.some(
            (m: ModelOption) => m.name === "gemini-3.5-flash-lite"
          );
          if (hasPrimary) setSelectedModel("gemini-3.5-flash-lite");
        }
      })
      .catch((err) => console.warn("Failed to load models:", err));
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const runExtraction = async () => {
    if (selectedFiles.length === 0) return;
    setIsExtracting(true);
    setStatusMessage("Extracting and verifying product data...");
    setExtractionErrors([]);

    const formData = new FormData();
    selectedFiles.forEach((file) => formData.append("files", file));
    formData.append("modelName", selectedModel);
    formData.append("reviewModel", reviewModel);
    formData.append("temperature", temperature.toString());

    try {
      const res = await fetch("/api/extract", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Extraction failed");

      setExtractedRows(data.rows || []);
      setRawExtractions(data.raw || []);
      setExtractionErrors(data.errors || []);
      setMetrics(data.metrics || null);
      setStatusMessage(
        `Extracted ${data.rows?.length || 0} items from ${selectedFiles.length} file(s).`
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`Error: ${msg}`);
    } finally {
      setIsExtracting(false);
    }
  };

  const handleCellChange = (
    index: number,
    field: keyof ExtractedRow,
    value: string | number | boolean | null
  ) => {
    const updated = [...extractedRows];
    updated[index] = { ...updated[index], [field]: value };
    setExtractedRows(updated);
  };

  const saveToDatabase = async () => {
    if (extractedRows.length === 0) return;
    setIsSaving(true);
    try {
      const res = await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: extractedRows }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Save failed");
      setStatusMessage(`Successfully saved ${data.inserted} new rows and updated ${data.updated} rows.`);
      setExtractedRows([]);
      setRawExtractions([]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`Failed to save: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  const loadDbData = async () => {
    setIsLoadingDb(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append("search", searchQuery);
      if (statusFilter === "needs_review") params.append("needs_review", "true");
      if (statusFilter === "verified") params.append("needs_review", "false");

      const res = await fetch(`/api/products?${params.toString()}`);
      const data = await res.json();
      setDbRows(data.rows || []);
      setTotalCount(data.total || 0);
      setQueryLatency(data.latency_ms || 0);
    } catch (err: unknown) {
      console.warn("Failed to fetch products:", err);
    } finally {
      setIsLoadingDb(false);
    }
  };

  useEffect(() => {
    if (activeTab === "data") {
      loadDbData();
    }
  }, [activeTab, statusFilter]);

  const downloadJson = (data: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadCsv = (rows: ExtractedRow[], filename: string) => {
    if (rows.length === 0) return;
    const headers = [
      "source_file",
      "product_name",
      "product_code",
      "quantity",
      "unit",
      "unit_price",
      "total_price",
      "currency",
      "supplier",
      "invoice_number",
      "needs_review",
      "review_notes",
      "confidence",
    ];
    const csvContent = [
      headers.join(","),
      ...rows.map((r) =>
        headers
          .map((h) => {
            const val = r[h as keyof ExtractedRow];
            const str = val === null || val === undefined ? "" : String(val);
            return `"${str.replace(/"/g, '""')}"`;
          })
          .join(",")
      ),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 font-sans">
      {/* Top Navbar */}
      <header className="border-b border-neutral-200 bg-white sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="bg-blue-600 text-white p-2 rounded-lg">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-neutral-900">
                Image to Text OCR
              </h1>
              <p className="text-xs text-neutral-500">
                Powered by Gemini 3.5 Flash Lite & Gemma 4 26B
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setActiveTab("extract")}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                activeTab === "extract"
                  ? "bg-blue-50 text-blue-700 font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              Extract & Verify
            </button>
            <button
              onClick={() => setActiveTab("data")}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                activeTab === "data"
                  ? "bg-blue-50 text-blue-700 font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              Saved Database
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === "extract" ? (
          <div className="space-y-8">
            {/* Control Panel */}
            <div className="bg-white p-6 rounded-xl border border-neutral-200 shadow-sm grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
                  Primary Vision Model
                </label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full border border-neutral-300 rounded-lg px-3 py-2 text-sm bg-neutral-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {models.map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.displayName}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-neutral-400 mt-1">
                  High-precision image OCR extraction
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
                  Review Model (Cross-Check)
                </label>
                <input
                  type="text"
                  value={reviewModel}
                  onChange={(e) => setReviewModel(e.target.value)}
                  className="w-full border border-neutral-300 rounded-lg px-3 py-2 text-sm bg-neutral-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-neutral-400 mt-1">
                  Text-to-text QA auditor for missing fields
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
                  Creativity / Temperature ({temperature})
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full mt-2"
                />
                <p className="text-xs text-neutral-400 mt-1">
                  Keep at 0 for strict factual OCR
                </p>
              </div>
            </div>

            {/* Upload Box */}
            <div className="bg-white p-8 rounded-xl border-2 border-dashed border-neutral-300 hover:border-blue-400 transition-colors text-center">
              <Upload className="w-10 h-10 text-neutral-400 mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-neutral-900">
                Upload image(s) or folder of product receipts
              </h3>
              <p className="text-xs text-neutral-500 mt-1 mb-4">
                Supports PNG, JPG, JPEG, WEBP, HEIC, HEIF
              </p>
              <input
                type="file"
                multiple
                accept="image/*"
                onChange={handleFileChange}
                className="block mx-auto text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
              />
              {selectedFiles.length > 0 && (
                <div className="mt-4 flex items-center justify-center space-x-2 text-sm text-neutral-600">
                  <FileText className="w-4 h-4 text-blue-600" />
                  <span>{selectedFiles.length} file(s) selected</span>
                </div>
              )}
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-between">
              <button
                onClick={runExtraction}
                disabled={selectedFiles.length === 0 || isExtracting}
                className="inline-flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white font-medium px-5 py-2.5 rounded-lg text-sm transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Sparkles className="w-4 h-4" />
                <span>{isExtracting ? "Extracting..." : "Extract and Verify"}</span>
              </button>

              {statusMessage && (
                <span className="text-sm text-neutral-600 bg-neutral-100 px-3 py-1.5 rounded-md">
                  {statusMessage}
                </span>
              )}
            </div>

            {/* Errors display */}
            {extractionErrors.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 p-4 rounded-lg space-y-1">
                <h4 className="text-xs font-semibold text-amber-800 uppercase tracking-wider">
                  Warnings / Skipped Items
                </h4>
                {extractionErrors.map((err, i) => (
                  <p key={i} className="text-xs text-amber-700">
                    {err}
                  </p>
                ))}
              </div>
            )}

            {/* Metrics overview */}
            {metrics && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white p-4 rounded-lg border border-neutral-200">
                  <span className="text-xs font-semibold text-neutral-400">Total Items Extracted</span>
                  <p className="text-2xl font-bold text-neutral-900 mt-1">{extractedRows.length}</p>
                </div>
                <div className="bg-white p-4 rounded-lg border border-neutral-200">
                  <span className="text-xs font-semibold text-neutral-400">Re-Reads Triggered</span>
                  <p className="text-2xl font-bold text-blue-600 mt-1">{metrics.reread_count}</p>
                </div>
                <div className="bg-white p-4 rounded-lg border border-neutral-200">
                  <span className="text-xs font-semibold text-neutral-400">Needs Review Flagged</span>
                  <p className="text-2xl font-bold text-amber-600 mt-1">{metrics.needs_review_count}</p>
                </div>
              </div>
            )}

            {/* Results Review Section */}
            {extractedRows.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-neutral-900">
                      Product Data Review Table
                    </h2>
                    <p className="text-xs text-neutral-500">
                      Editable grid. Double click to modify any values before saving.
                    </p>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => downloadJson(rawExtractions, "extractions.json")}
                      className="inline-flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-neutral-900 bg-white border border-neutral-200 px-3 py-1.5 rounded-md"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download JSON</span>
                    </button>
                    <button
                      onClick={() => downloadCsv(extractedRows, "extracted_products.csv")}
                      className="inline-flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-neutral-900 bg-white border border-neutral-200 px-3 py-1.5 rounded-md"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download CSV</span>
                    </button>
                    <button
                      onClick={saveToDatabase}
                      disabled={isSaving}
                      className="inline-flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium px-4 py-1.5 rounded-md text-xs transition-colors"
                    >
                      <Save className="w-3.5 h-3.5" />
                      <span>{isSaving ? "Saving..." : "Save to Database"}</span>
                    </button>
                  </div>
                </div>

                <div className="bg-white border border-neutral-200 rounded-xl overflow-hidden shadow-sm overflow-x-auto">
                  <table className="min-w-full divide-y divide-neutral-200 text-xs">
                    <thead className="bg-neutral-50">
                      <tr>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Product Name</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Code / SKU</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Qty</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Unit</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Unit Price</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Total Price</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Currency</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Status</th>
                        <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Supplier</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100 bg-white">
                      {extractedRows.map((r, i) => (
                        <tr key={i} className="hover:bg-neutral-50">
                          <td className="px-3 py-2">
                            <input
                              type="text"
                              value={r.product_name}
                              onChange={(e) => handleCellChange(i, "product_name", e.target.value)}
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-blue-500 rounded px-1"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="text"
                              value={r.product_code}
                              onChange={(e) => handleCellChange(i, "product_code", e.target.value)}
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-blue-500 rounded px-1"
                            />
                          </td>
                          <td className="px-3 py-2 w-20">
                            <input
                              type="number"
                              value={r.quantity}
                              onChange={(e) =>
                                handleCellChange(i, "quantity", parseFloat(e.target.value) || 0)
                              }
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-blue-500 rounded px-1"
                            />
                          </td>
                          <td className="px-3 py-2 w-20">
                            <input
                              type="text"
                              value={r.unit}
                              onChange={(e) => handleCellChange(i, "unit", e.target.value)}
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-blue-500 rounded px-1"
                            />
                          </td>
                          <td className="px-3 py-2 w-28">
                            <input
                              type="number"
                              value={r.unit_price ?? ""}
                              onChange={(e) =>
                                handleCellChange(
                                  i,
                                  "unit_price",
                                  e.target.value ? parseFloat(e.target.value) : null
                                )
                              }
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-blue-500 rounded px-1"
                            />
                          </td>
                          <td className="px-3 py-2 w-28">
                            <input
                              type="number"
                              value={r.total_price ?? ""}
                              onChange={(e) =>
                                handleCellChange(
                                  i,
                                  "total_price",
                                  e.target.value ? parseFloat(e.target.value) : null
                                )
                              }
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-blue-500 rounded px-1"
                            />
                          </td>
                          <td className="px-3 py-2 w-20">
                            <span className="text-neutral-600 px-1">{r.currency}</span>
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap">
                            {r.needs_review ? (
                              <span className="inline-flex items-center text-amber-700 bg-amber-50 px-2 py-0.5 rounded text-[11px] font-medium">
                                <AlertTriangle className="w-3 h-3 mr-1" />
                                Needs Review
                              </span>
                            ) : (
                              <span className="inline-flex items-center text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-medium">
                                <CheckCircle2 className="w-3 h-3 mr-1" />
                                Verified
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-neutral-500">{r.supplier || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Database Explorer Tab */
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl border border-neutral-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
              <div className="flex items-center space-x-3 w-full md:w-auto">
                <div className="relative flex-1 md:w-80">
                  <Search className="w-4 h-4 text-neutral-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search product name, code, notes..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-xs border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="text-xs border border-neutral-300 rounded-lg px-3 py-2 bg-neutral-50"
                >
                  <option value="all">All Status</option>
                  <option value="verified">Verified</option>
                  <option value="needs_review">Needs Review</option>
                </select>
                <button
                  onClick={loadDbData}
                  className="bg-neutral-100 hover:bg-neutral-200 p-2 rounded-lg text-neutral-600 transition-colors"
                >
                  <RotateCw className="w-4 h-4" />
                </button>
              </div>

              <div className="flex items-center space-x-4 text-xs text-neutral-500">
                <span>Total: <strong className="text-neutral-900">{totalCount}</strong> rows</span>
                <span>Latency: <strong className="text-neutral-900">{queryLatency} ms</strong></span>
                <button
                  onClick={() => downloadCsv(dbRows, "database_products.csv")}
                  className="inline-flex items-center space-x-1.5 text-blue-600 hover:text-blue-700 font-medium"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Export CSV</span>
                </button>
              </div>
            </div>

            {/* DB Table */}
            <div className="bg-white border border-neutral-200 rounded-xl overflow-hidden shadow-sm overflow-x-auto">
              <table className="min-w-full divide-y divide-neutral-200 text-xs">
                <thead className="bg-neutral-50">
                  <tr>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">ID</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Product Name</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Code / SKU</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Qty</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Unit</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Unit Price</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Total Price</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Status</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-neutral-600">Notes / Audit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 bg-white">
                  {dbRows.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-neutral-400">
                        {isLoadingDb ? "Loading records..." : "No records found in database."}
                      </td>
                    </tr>
                  ) : (
                    dbRows.map((r, i) => (
                      <tr key={r.id || i} className="hover:bg-neutral-50">
                        <td className="px-3 py-2 text-neutral-400 font-mono">{r.id}</td>
                        <td className="px-3 py-2 font-medium text-neutral-900">{r.product_name}</td>
                        <td className="px-3 py-2 font-mono text-neutral-600">{r.product_code || "-"}</td>
                        <td className="px-3 py-2">{r.quantity}</td>
                        <td className="px-3 py-2">{r.unit || "-"}</td>
                        <td className="px-3 py-2">
                          {r.unit_price ? `${r.unit_price.toLocaleString()} ${r.currency}` : "-"}
                        </td>
                        <td className="px-3 py-2">
                          {r.total_price ? `${r.total_price.toLocaleString()} ${r.currency}` : "-"}
                        </td>
                        <td className="px-3 py-2">
                          {r.needs_review ? (
                            <span className="inline-flex items-center text-amber-700 bg-amber-50 px-2 py-0.5 rounded text-[11px] font-medium">
                              Needs Review
                            </span>
                          ) : (
                            <span className="inline-flex items-center text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-medium">
                              Verified
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-neutral-500 max-w-xs truncate">
                          {r.review_notes || r.notes || "-"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
