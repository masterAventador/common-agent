import axios from "axios";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiClient = axios.create({
  baseURL: configuredBaseUrl || "http://127.0.0.1:18200/api/v1",
  timeout: 10_000,
  headers: {
    Accept: "application/json",
  },
});
