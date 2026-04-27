"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  FileText,
  FlaskConical,
  Pill,
  Plus,
  ScanLine,
  Trash2,
  X,
} from "lucide-react";

import {
  api,
  type MedicationRead,
  type PatientFullProfile,
  type PatientUploadRead,
  type SymptomRead,
} from "@/lib/api";
import { VolumeViewer } from "@/components/VolumeViewer";

/**
 * Patient profile.
 *
 * Visual: paper white + ink black with one accent (gold). Each section has
 * an icon, a count badge, and an inline + button at the right. The page
 * reads as one continuous scroll punctuated by gold seams.
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
  if (profile.isError) return <Centered>Patient not found.</Centered>;
  if (!profile.data) return null;

  const { patient, medications, symptoms, uploads } = profile.data;
  const initial = patient.name.slice(0, 1).toUpperCase();

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
        {/* Header — circular avatar + name + meta */}
        <div className="flex items-center gap-5">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-amber-200 to-amber-500 flex items-center justify-center text-2xl font-semibold text-white shadow-sm">
            {initial}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">
              {patient.name}
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Age {patient.age} · {patient.indication}
            </p>
          </div>
        </div>

        {/* Quick-stats row */}
        <div className="grid grid-cols-3 gap-3">
          <Stat icon={<Pill className="w-4 h-4" />} count={medications.length} label="medications" />
          <Stat icon={<Activity className="w-4 h-4" />} count={symptoms.length} label="symptoms" />
          <Stat icon={<FileText className="w-4 h-4" />} count={uploads.length} label="records" />
        </div>

        <Section
          icon={<Pill className="w-4 h-4" />}
          title="Medications"
          count={medications.length}
          add={(open) => (
            <AddInline open={open} render={(close) => <AddMedicationForm patientId={patientId} onDone={close} />} />
          )}
        >
          {medications.length === 0 ? (
            <Empty>No medications yet.</Empty>
          ) : (
            medications.map((m) => (
              <MedicationRow key={m.id} patientId={patientId} med={m} />
            ))
          )}
        </Section>

        <Section
          icon={<Activity className="w-4 h-4" />}
          title="Symptoms"
          count={symptoms.length}
          add={(open) => (
            <AddInline open={open} render={(close) => <AddSymptomForm patientId={patientId} onDone={close} />} />
          )}
        >
          {symptoms.length === 0 ? (
            <Empty>No symptoms logged.</Empty>
          ) : (
            symptoms.map((s) => (
              <SymptomRow key={s.id} patientId={patientId} sym={s} />
            ))
          )}
        </Section>

        <Section
          icon={<FileText className="w-4 h-4" />}
          title="Records"
          count={uploads.length}
          add={null}
        >
          {uploads.length === 0 ? (
            <Empty>
              Upload from{" "}
              <Link href="/build" className="text-primary hover:underline">
                /build
              </Link>{" "}
              and they appear here.
            </Empty>
          ) : (
            uploads.map((u) => <UploadRow key={u.id} upload={u} />)
          )}
        </Section>
      </main>
    </div>
  );
}

// ---------- Section primitives ----------

function Stat({
  icon,
  count,
  label,
}: {
  icon: React.ReactNode;
  count: number;
  label: string;
}) {
  return (
    <div className="border rounded-xl p-4 bg-card">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-xs uppercase tracking-wide">{label}</span>
      </div>
      <div className="mt-1 text-2xl font-semibold">{count}</div>
    </div>
  );
}

function Section({
  icon,
  title,
  count,
  add,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  add: ((open: boolean) => React.ReactNode) | null;
  children: React.ReactNode;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <section className="space-y-3">
      <div className="h-px bg-gradient-to-r from-amber-400/40 via-amber-500 to-amber-400/40" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">{icon}</span>
          <h2 className="text-lg font-semibold">{title}</h2>
          {count > 0 ? (
            <span className="text-xs text-muted-foreground">· {count}</span>
          ) : null}
        </div>
        {add ? (
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
            aria-label={adding ? "Cancel" : "Add"}
          >
            {adding ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            {adding ? "Cancel" : "Add"}
          </button>
        ) : null}
      </div>
      {add ? add(adding) : null}
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function AddInline({
  open,
  render,
}: {
  open: boolean;
  render: (close: () => void) => React.ReactNode;
}) {
  // Render is gated outside; this just wraps to capture the close callback.
  if (!open) return null;
  return render(() => undefined);
}

// ---------- Medication ----------

function MedicationRow({
  patientId,
  med,
}: {
  patientId: string;
  med: MedicationRead;
}) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.deleteMedication(patientId, med.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", patientId] }),
  });
  const active = !med.ended_at;
  return (
    <Row>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-medium">{med.drug_name}</span>
          {med.dose ? (
            <span className="text-xs text-muted-foreground">{med.dose}</span>
          ) : null}
          {active ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium uppercase tracking-wide">
              Active
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-medium uppercase tracking-wide">
              Past
            </span>
          )}
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {med.started_at ?? "Started date unknown"}
          {med.ended_at ? ` → ${med.ended_at}` : null}
          {med.notes ? ` · ${med.notes}` : null}
        </div>
      </div>
      <DeleteButton onClick={() => remove.mutate()} label="Remove medication" />
    </Row>
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
      className="border rounded-xl p-3 bg-amber-50/30 space-y-2"
    >
      <Input value={drugName} onChange={setDrugName} placeholder="Drug name *" autoFocus />
      <div className="grid grid-cols-2 gap-2">
        <Input value={dose} onChange={setDose} placeholder="Dose (e.g. 300 mg twice daily)" />
        <Input value={startedAt} onChange={setStartedAt} type="date" />
      </div>
      <Input value={notes} onChange={setNotes} placeholder="Notes" />
      <SaveBar disabled={!drugName.trim() || add.isPending} />
    </form>
  );
}

// ---------- Symptom ----------

function SymptomRow({
  patientId,
  sym,
}: {
  patientId: string;
  sym: SymptomRead;
}) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.deleteSymptom(patientId, sym.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", patientId] }),
  });
  return (
    <Row>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-medium">{sym.label}</span>
          <SeverityPill severity={sym.severity} />
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {sym.occurred_on}
          {sym.notes ? ` · ${sym.notes}` : null}
        </div>
      </div>
      <DeleteButton onClick={() => remove.mutate()} label="Remove symptom" />
    </Row>
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
      className="border rounded-xl p-3 bg-amber-50/30 space-y-2"
    >
      <Input value={label} onChange={setLabel} placeholder="What happened? *" autoFocus />
      <div className="grid grid-cols-2 gap-2">
        <Input value={date} onChange={setDate} type="date" />
        <label className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground uppercase tracking-wide">Severity</span>
          <input
            type="range"
            min={1}
            max={10}
            value={severity}
            onChange={(e) => setSeverity(Number(e.target.value))}
            className="flex-1"
          />
          <span className="font-mono w-6 text-right">{severity}</span>
        </label>
      </div>
      <Input value={notes} onChange={setNotes} placeholder="Notes" />
      <SaveBar disabled={!label.trim() || add.isPending} />
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

// ---------- Upload ----------

function UploadRow({ upload }: { upload: PatientUploadRead }) {
  const kindIcons: Record<PatientUploadRead["upload_kind"], React.ReactNode> = {
    ct_scan: <ScanLine className="w-4 h-4 text-primary" />,
    vcf: <FlaskConical className="w-4 h-4 text-primary" />,
    "23andme": <FlaskConical className="w-4 h-4 text-primary" />,
    report: <FileText className="w-4 h-4 text-primary" />,
  };
  const kindLabels: Record<PatientUploadRead["upload_kind"], string> = {
    ct_scan: "CT scan",
    vcf: "Genetic data (VCF)",
    "23andme": "23andMe",
    report: "Report",
  };
  const isViewableCt =
    upload.upload_kind === "ct_scan" && !!upload.asset_url;

  return (
    <div className="border rounded-xl bg-card overflow-hidden hover:border-amber-200 transition-colors">
      <div className="flex items-start gap-3 p-3">
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
          {kindIcons[upload.upload_kind]}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{upload.filename}</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {kindLabels[upload.upload_kind]} ·{" "}
            {new Date(upload.uploaded_at).toLocaleDateString()}
            {upload.summary_json ? ` · ${upload.summary_json}` : null}
          </div>
        </div>
      </div>
      {isViewableCt ? (
        <div className="bg-black h-[320px] border-t">
          <VolumeViewer volumeUrl={upload.asset_url!} />
        </div>
      ) : null}
    </div>
  );
}

// ---------- Shared bits ----------

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 border rounded-xl p-3 bg-card hover:border-amber-200 transition-colors">
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-sm text-muted-foreground italic px-3 py-2">
      {children}
    </div>
  );
}

function DeleteButton({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-muted-foreground hover:text-red-600 transition-colors p-1 flex-shrink-0"
      aria-label={label}
    >
      <Trash2 className="w-4 h-4" />
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

function SaveBar({ disabled }: { disabled?: boolean }) {
  return (
    <div className="flex items-center justify-end pt-1">
      <button
        type="submit"
        disabled={disabled}
        className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm hover:opacity-90 disabled:opacity-50"
      >
        Save
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
