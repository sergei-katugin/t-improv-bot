export function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const demoMutation = import.meta.env.DEV &&
    new URLSearchParams(location.search).get("preview") === "1" &&
    init.method && init.method !== "GET";
  if (demoMutation) return Promise.resolve({ id: Date.now(), isActive: true } as T);
  const initData = window.Telegram?.WebApp.initData ?? "";
  if (!initData) {
    return Promise.reject(new Error("Telegram не передал данные авторизации. Закрой Mini App и открой его свежей кнопкой из админ-бота."));
  }
  const isForm = init.body instanceof FormData;
  return fetch(path, {
    ...init,
    headers: { ...(!isForm && { "Content-Type": "application/json" }), Authorization: `tma ${initData}`, ...init.headers },
  }).then(async (response) => {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const requestId = response.headers.get("X-Request-ID") ?? payload.requestId;
      const message = response.status === 401 ? "Открой Mini App из админ-бота" :
        response.status === 403 ? "Недостаточно прав для этого действия" :
        payload.field ? `Проверь поле: ${payload.field}` : "Не удалось выполнить запрос";
      throw new Error(`${message}${requestId ? ` · код ${requestId}` : ""}`);
    }
    return response.json() as Promise<T>;
  });
}

export async function authenticatedBlob(path: string): Promise<Blob> {
  const initData = window.Telegram?.WebApp.initData ?? "";
  if (!initData) throw new Error("Telegram не передал данные авторизации");
  const response = await fetch(path, { headers: { Authorization: `tma ${initData}` } });
  if (!response.ok) {
    const requestId = response.headers.get("X-Request-ID");
    throw new Error(`Не удалось загрузить файл${requestId ? ` · код ${requestId}` : ""}`);
  }
  return response.blob();
}
