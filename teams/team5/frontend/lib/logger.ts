type LogLevel = "debug" | "info" | "warn" | "error";

function log(level: LogLevel, component: string, message: string, extra?: unknown) {
  const ts = new Date().toISOString();
  const prefix = `${ts} | ${level.toUpperCase().padEnd(5)} | ${component}`;
  const fn = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
  if (extra !== undefined) {
    fn(prefix, "|", message, extra);
  } else {
    fn(prefix, "|", message);
  }
}

export const logger = {
  debug: (component: string, msg: string, extra?: unknown) => log("debug", component, msg, extra),
  info:  (component: string, msg: string, extra?: unknown) => log("info", component, msg, extra),
  warn:  (component: string, msg: string, extra?: unknown) => log("warn", component, msg, extra),
  error: (component: string, msg: string, extra?: unknown) => log("error", component, msg, extra),
};
