"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";

import {
  api,
  type MedicationRead,
  type PatientFullProfile,
  type PatientUploadRead,
  type SymptomRead,
} from "@/lib/api";

/**
 * Patient profile.
 *
 * Kintsugi visual principles applied:
 *   - Restrained palette (paper white + ink black) with one accent: gold,
 *     used as the seam between sections.
 *   - Minimal copy. Headers are short noun phrases; helper text is a
 *     single short sentence at most.
 *   - The "cracks" (missing data, low-confidence calls, severity rows) are
 *     surfaced honestly — that's what makes the gold visible.
 */
export default function PatientProfilePage() {
  const params = useParams<{ id: string }>();
  const patientId = params?.id ?? "";

  const profile = useQuery<PatientFullProfile>({
    queryKey: ["patient", patientId],
    queryFn: () => api.getPatientProfile(patientId),
    enabled: !!patientId,
  });

  if (profile.isLoading) return <Centered>Loading.</Centered>;
  if (profile.isError)
    return <Centered>Patient not found.</Centered>;
  if (!profile.data) return null;

  const { patient, medications, symptoms, uploads } = profile.data;

  return (
    <div className="bg-white min-h-screen">
      <header className="border-b">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link
            href="/demo"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ← All patients
          </Link>
          <Link
            href={`/walkthrough/${patient.id}`}
            className="text-sm text-primary hover:underline"
          >
            See clinical analysis
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 space-y-10">
        <ProfileHeader patient={patient} />

        <Section title="Medications" subtitle="What you're taking now and what you've been on.">
          <MedicationsList patientId={patientId} medications={medications} />
        </Section>

        <Section title="Symptoms" subtitle="Track what you're feeling between appointments.">
          <SymptomsList patientId={patientId} symptoms={symptoms} />
        </Section>

        <Section title="Records" subtitle="Files you've uploaded — scans, lab reports, sequencing.">
          <UploadsList uploads={uploads} />
        </Section>
      </main>
    </div>
  );
}

function ProfileHeader({ patient }: { patient: PatientFullProfile["patient"] }) {
  return (
    <div className="space-y-2">
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">
        {patient.name}
      </h1>
      <div className="text-sm text-muted-foreground space-y-0.5">
        <div>Age {patient.age}.</div>
        <div>{patient.indication}.</div>
      </div>
    </div>
  );
}

/**
 * Section card with a kintsugi seam — a thin gold divider on top, then the
 * heading + content. Replaces every section's bordered box on the page so
 * the page reads like one continuous scroll punctuated by gold.
 */
function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="h-px bg-gradient-to-r from-amber-400/40 via-amber-500 to-amber-400/40" />
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {subtitle ? (
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

// ---------- Medications ----------

function MedicationsList({
  patientId,
  medications,
}: {
  patientId: string;
  medications: MedicationRead[];
}) {
  const [adding, setAdding] = useState(false);
  const qc = useQueryClient();

  const remove = useMutation({
    mutationFn: (medId: number) => api.deleteMedication(patientId, medId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", patientId] }),
  });

  return (
    <div className="space-y-2">
      {medications.length === 0 ? (
        <Empty>No medications recorded.</Empty>
      ) : (
        medications.map((m) => (
          <Row key={m.id}>
            <div className="flex-1 min-w-0">
              <div className="font-medium">
                {m.drug_name}
                {m.dose ? (
                  <span className="text-muted-foreground font-normal"> · {m.dose}</span>
                ) : null}
              </div>
              <div className="text-xs text-muted-foreground">
                {m.started_at ? `Started ${m.started_at}` : "Started date unknown"}
                {m.ended_at ? ` → ${m.ended_at}` : null}
                {m.notes ? ` · ${m.notes}` : null}
              </div>
            </div>
            <button
              type="button"
              onClick={() => remove.mutate(m.id)}
              className="text-muted-foreground hover:text-red-600 transition-colors p-1"
              aria-label="Remove medication"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </Row>
        ))
      )}
      {adding ? (
        <AddMedicationForm
          patientId={patientId}
          onDone={() => setAdding(false)}
        />
      ) : (
        <AddButton onClick={() => setAdding(true)}>Add medication</AddButton>
      )}
    </div>
  );
}

function AddMedicationForm({
  patientId,
  onDone,
}: {
  patientId: string;
  onDone: () => void;
}) {
  const [drugName, setDrugName] = useState("");
  const [dose, setDose] = useState("");
  const [startedAt, setStartedAt] = useState("");
  const [notes, setNotes] = useState("");
  const qc = useQueryClient();

  const add = useMutation({
    mutationFn: () =>
      api.addMedication(patientId, {
        drug_name: drugName.trim(),
        dose: dose.trim() || null,
        started_at: startedAt || null,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patient", patientId] });
      onDone();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (drugName.trim()) add.mutate();
      }}
      className="border rounded-xl p-3 bg-card space-y-2"
    >
      <Input value={drugName} onChange={setDrugName} placeholder="Drug name *" autoFocus />
      <div className="grid grid-cols-2 gap-2">
        <Input value={dose} onChange={setDose} placeholder="Dose (e.g. 300 mg twice daily)" />
        <Input
          value={startedAt}
          onChange={setStartedAt}
          placeholder="YYYY-MM-DD"
          type="date"
        />
      </div>
      <Input value={notes} onChange={setNotes} placeholder="Notes (optional)" />
      <FormActions onCancel={onDone} disabled={!drugName.trim() || add.isPending} />
    </form>
  );
}

// ---------- Symptoms ----------

function SymptomsList({
  patientId,
  symptoms,
}: {
  patientId: string;
  symptoms: SymptomRead[];
}) {
  const [adding, setAdding] = useState(false);
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteSymptom(patientId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", patientId] }),
  });

  return (
    <div className="space-y-2">
      {symptoms.length === 0 ? (
        <Empty>No symptoms recorded yet.</Empty>
      ) : (
        symptoms.map((s) => (
          <Row key={s.id}>
            <div className="flex-1 min-w-0">
              <div className="font-medium flex items-center gap-2">
                {s.label}
                <SeverityPill severity={s.severity} />
              </div>
              <div className="text-xs text-muted-foreground">
                {s.occurred_on}
                {s.notes ? ` · ${s.notes}` : null}
              </div>
            </div>
            <button
              type="button"
              onClick={() => remove.mutate(s.id)}
              className="text-muted-foreground hover:text-red-600 transition-colors p-1"
              aria-label="Remove symptom"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </Row>
        ))
      )}
      {adding ? (
        <AddSymptomForm patientId={patientId} onDone={() => setAdding(false)} />
      ) : (
        <AddButton onClick={() => setAdding(true)}>Log symptom</AddButton>
      )}
    </div>
  );
}

function AddSymptomForm({
  patientId,
  onDone,
}: {
  patientId: string;
  onDone: () => void;
}) {
  const [label, setLabel] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [severity, setSeverity] = useState(5);
  const [notes, setNotes] = useState("");
  const qc = useQueryClient();

  const add = useMutation({
    mutationFn: () =>
      api.addSymptom(patientId, {
        occurred_on: date,
        label: label.trim(),
        severity,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patient", patientId] });
      onDone();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (label.trim()) add.mutate();
      }}
      className="border rounded-xl p-3 bg-card space-y-2"
    >
      <Input value={label} onChange={setLabel} placeholder="What happened? *" autoFocus />
      <div className="grid grid-cols-2 gap-2">
        <Input value={date} onChange={setDate} type="date" />
        <label className="flex items-center gap-2 text-sm">
          <span className="text-xs text-muted-foreground">Severity</span>
          <input
            type="range"
            min={1}
            max={10}
            value={severity}
            onChange={(e) => setSeverity(Number(e.target.value))}
            className="flex-1"
          />
          <span className="font-mono text-xs w-6 text-right">{severity}</span>
        </label>
      </div>
      <Input value={notes} onChange={setNotes} placeholder="Notes (optional)" />
      <FormActions onCancel={onDone} disabled={!label.trim() || add.isPending} />
    </form>
  );
}

function SeverityPill({ severity }: { severity: number }) {
  const tone =
    severity >= 7
      ? "bg-red-100 text-red-800"
      : severity >= 4
        ? "bg-amber-100 text-amber-800"
        : "bg-emerald-100 text-emerald-800";
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${tone}`}>
      {severity}/10
    </span>
  );
}

// ---------- Uploads ----------

function UploadsList({ uploads }: { uploads: PatientUploadRead[] }) {
  if (uploads.length === 0) {
    return (
      <Empty>
        Upload a CT scan, VCF, or 23andMe file from{" "}
        <Link href="/build" className="text-primary hover:underline">
          /build
        </Link>{" "}
        — once analysed, it&apos;ll appear here.
      </Empty>
    );
  }
  return (
    <div className="space-y-2">
      {uploads.map((u) => (
        <Row key={u.id}>
          <div className="flex-1 min-w-0">
            <div className="font-medium truncate">{u.filename}</div>
            <div className="text-xs text-muted-foreground">
              {u.upload_kind.replace("_", " ")} · {new Date(u.uploaded_at).toLocaleDateString()}
              {u.summary_json ? ` · ${u.summary_json}` : null}
            </div>
          </div>
          {u.asset_url ? (
            <a
              href={u.asset_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:underline whitespace-nowrap"
            >
              View
            </a>
          ) : null}
        </Row>
      ))}
    </div>
  );
}

// ---------- Shared bits ----------

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 border rounded-xl p-3 bg-card">
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-sm text-muted-foreground italic px-1">{children}</div>
  );
}

function AddButton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
    >
      <Plus className="w-3.5 h-3.5" /> {children}
    </button>
  );
}

function Input({
  value,
  onChange,
  ...props
}: {
  value: string;
  onChange: (v: string) => void;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full border rounded-md px-3 py-1.5 text-sm bg-white"
      {...props}
    />
  );
}

function FormActions({
  onCancel,
  disabled,
}: {
  onCancel: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 pt-1">
      <button
        type="submit"
        disabled={disabled}
        className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm hover:opacity-90 disabled:opacity-50"
      >
        Save
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        Cancel
      </button>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[60vh] flex items-center justify-center text-muted-foreground">
      {children}
    </div>
  );
}
