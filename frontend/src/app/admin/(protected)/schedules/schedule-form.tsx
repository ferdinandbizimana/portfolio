"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field, StatusMessage } from "@/components/admin/fields";
import { sendJson } from "@/lib/api-errors";
import type { AnalysisInfo } from "@/lib/runs";
import {
  isDateRule,
  WEEKDAYS,
  type ParameterValue,
  type Schedule,
  type ScheduleOptions,
} from "@/lib/schedules";

type InputRule = { pattern: string; sheet: string };
const FIXED = "fixed";

function defaultParameters(analysis: AnalysisInfo | undefined): Record<string, ParameterValue> {
  const properties = analysis?.parameters_schema.properties ?? {};
  return Object.fromEntries(
    Object.entries(properties)
      .filter(([, prop]) => prop.format === "date")
      .map(([name]) => [name, { rule: "previous_month_end" }]),
  );
}

export function ScheduleForm({
  analyses,
  options,
  schedule,
}: {
  analyses: AnalysisInfo[];
  options: ScheduleOptions;
  schedule?: Schedule;
}) {
  const router = useRouter();
  const [name, setName] = useState(schedule?.name ?? "");
  const [analysisKey, setAnalysisKey] = useState(schedule?.analysis ?? analyses[0]?.key ?? "");
  const analysis = analyses.find((a) => a.key === analysisKey);
  const [enabled, setEnabled] = useState(schedule?.enabled ?? true);
  const [trigger, setTrigger] = useState<"daily" | "new_files">(schedule?.trigger ?? "daily");
  const [runTime, setRunTime] = useState(schedule?.run_time ?? "06:00");
  const [weekdays, setWeekdays] = useState<number[]>(schedule?.weekdays ?? [0, 1, 2, 3, 4, 5, 6]);
  const [inputs, setInputs] = useState<Record<string, InputRule>>(schedule?.inputs ?? {});
  const [parameters, setParameters] = useState<Record<string, ParameterValue>>(
    schedule?.parameters ?? defaultParameters(analysis),
  );
  const [onlyWhenChanged, setOnlyWhenChanged] = useState(schedule?.only_when_changed ?? true);
  const [notify, setNotify] = useState(schedule?.notify ?? true);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  function chooseAnalysis(key: string) {
    setAnalysisKey(key);
    setInputs({});
    setParameters(defaultParameters(analyses.find((a) => a.key === key)));
  }

  function toggleDay(day: number) {
    setWeekdays((days) =>
      days.includes(day) ? days.filter((d) => d !== day) : [...days, day].sort(),
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    const body = {
      name,
      analysis: analysisKey,
      enabled,
      trigger,
      run_time: runTime,
      weekdays,
      inputs: Object.fromEntries(Object.entries(inputs).filter(([, rule]) => rule.pattern.trim())),
      parameters,
      only_when_changed: onlyWhenChanged,
      notify,
    };
    const result = schedule
      ? await sendJson<Schedule>("PUT", `/api/admin/schedules/${schedule.id}`, body)
      : await sendJson<Schedule>("POST", "/api/admin/schedules", body);
    setPending(false);
    if (!result.ok) {
      setMessage({ kind: "error", text: result.message });
      return;
    }
    router.push("/admin/schedules");
    router.refresh();
  }

  const properties = analysis?.parameters_schema.properties ?? {};

  return (
    <form onSubmit={onSubmit} className="flex max-w-2xl flex-col gap-6">
      <Field label="Name" hint="For example: Monthly closing stock.">
        <input
          className="input"
          required
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field label="Analysis">
        <select
          className="input"
          value={analysisKey}
          onChange={(e) => chooseAnalysis(e.target.value)}
        >
          {analyses.map((a) => (
            <option key={a.key} value={a.key}>
              {a.title}
            </option>
          ))}
        </select>
      </Field>

      <fieldset className="flex flex-col gap-3 rounded-lg border border-line p-4 text-sm">
        <legend className="px-1 font-semibold">When</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="trigger"
            checked={trigger === "daily"}
            onChange={() => setTrigger("daily")}
          />
          At a set time
        </label>
        {trigger === "daily" && (
          <div className="flex flex-col gap-3 pl-6">
            <Field label={`Time (${options.timezone})`}>
              <input
                className="input max-w-40"
                type="time"
                required
                value={runTime}
                onChange={(e) => setRunTime(e.target.value)}
              />
            </Field>
            <div className="flex flex-wrap gap-3" role="group" aria-label="Days">
              {WEEKDAYS.map((label, day) => (
                <label key={label} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={weekdays.includes(day)}
                    onChange={() => toggleDay(day)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={onlyWhenChanged}
                onChange={(e) => setOnlyWhenChanged(e.target.checked)}
              />
              Skip the run when no file has changed since the last one
            </label>
          </div>
        )}
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="trigger"
            checked={trigger === "new_files"}
            onChange={() => setTrigger("new_files")}
          />
          As soon as new files arrive in the shared folder
        </label>
      </fieldset>

      {analysis?.inputs.map((input) => {
        const rule = inputs[input.key] ?? { pattern: "", sheet: "" };
        const update = (change: Partial<InputRule>) =>
          setInputs({ ...inputs, [input.key]: { ...rule, ...change } });
        return (
          <fieldset
            key={input.key}
            className="flex flex-col gap-3 rounded-lg border border-line p-4"
          >
            <legend className="px-1 text-sm font-semibold">{input.label}</legend>
            <p className="text-xs text-muted">
              Expected: {input.dataset_title}. The newest ready file whose name matches is used.
            </p>
            <Field label="File name pattern" hint="* stands for any text, e.g. MB52*.xlsx">
              <input
                className="input"
                required={input.required}
                maxLength={200}
                value={rule.pattern}
                onChange={(e) => update({ pattern: e.target.value })}
              />
            </Field>
            {input.all_sheets ? (
              <p className="text-xs text-muted">
                Every sheet of the file recognised as this dataset is used.
              </p>
            ) : (
              <Field label="Sheet" hint="Leave empty to use the sheet recognised as this dataset.">
                <input
                  className="input"
                  maxLength={100}
                  value={rule.sheet}
                  onChange={(e) => update({ sheet: e.target.value })}
                />
              </Field>
            )}
          </fieldset>
        );
      })}

      {Object.entries(properties).map(([param, prop]) => {
        const value = parameters[param];
        const label = prop.title ?? param;
        if (prop.format === "date") {
          const mode = isDateRule(value) ? value.rule : FIXED;
          return (
            <fieldset key={param} className="flex flex-col gap-2 text-sm">
              <legend className="mb-1 font-medium">{label}</legend>
              <select
                className="input"
                aria-label={`${label}: rule`}
                value={mode}
                onChange={(e) =>
                  setParameters({
                    ...parameters,
                    [param]: e.target.value === FIXED ? "" : { rule: e.target.value },
                  })
                }
              >
                {Object.entries(options.date_rules).map(([rule, text]) => (
                  <option key={rule} value={rule}>
                    {text}
                  </option>
                ))}
                <option value={FIXED}>A fixed date</option>
              </select>
              {mode === FIXED && (
                <input
                  className="input"
                  type="date"
                  aria-label={`${label}: date`}
                  required
                  value={typeof value === "string" ? value : ""}
                  onChange={(e) => setParameters({ ...parameters, [param]: e.target.value })}
                />
              )}
            </fieldset>
          );
        }
        return (
          <Field key={param} label={label} hint={prop.description}>
            <input
              className="input"
              type={prop.type === "number" ? "number" : "text"}
              value={isDateRule(value) || value === undefined ? "" : String(value)}
              onChange={(e) => setParameters({ ...parameters, [param]: e.target.value })}
            />
          </Field>
        );
      })}

      <div className="flex flex-col gap-2 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
          E-mail me when a run of this schedule finishes
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Switched on
        </label>
      </div>

      <StatusMessage message={message} />
      <div>
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Saving…" : "Save schedule"}
        </button>
      </div>
    </form>
  );
}
