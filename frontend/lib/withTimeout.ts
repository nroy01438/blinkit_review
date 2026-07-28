/** Vercel functions have a hard time limit — one slow/unresponsive external
 * site must not be able to eat the whole sync's budget and take every other
 * source down with it. Races a connector call against a timeout and returns
 * the fallback (empty list) instead of hanging. */
export async function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  let timer: NodeJS.Timeout;
  const timeout = new Promise<T>((resolve) => {
    timer = setTimeout(() => resolve(fallback), ms);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timer!);
  }
}
