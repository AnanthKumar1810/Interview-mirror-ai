import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { PageHeader, Panel, PanelTitle } from "@/components/im/bits";
import { LANGUAGES } from "@/lib/im/data";
import { actions, useAppStore } from "@/lib/im/store";
import type { LangCode, Profile } from "@/lib/im/types";

export const Route = createFileRoute("/app/settings")({
  head: () => ({
    meta: [
      { title: "Settings — InterviewMirror" },
      {
        name: "description",
        content: "Update your profile, default interview language, voice options and saved data.",
      },
      { property: "og:title", content: "Settings — InterviewMirror" },
      { property: "og:description", content: "Profile, voice and data settings." },
    ],
  }),
  component: SettingsPage,
});

function SettingsPage() {
  const profile = useAppStore((s) => s.profile);
  const sessions = useAppStore((s) => s.sessions);
  const [form, setForm] = useState<Profile>(profile);
  useEffect(() => setForm(profile), [profile]);

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    actions.updateProfile({ ...form, name: form.name.trim() || "Candidate" });
    actions.updateSetup({ languageCode: form.language, targetRole: form.targetRole });
    toast.success("Settings saved");
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Settings"
        title="Profile & preferences"
        description="These defaults are used whenever you set up a new interview."
      />

      <form onSubmit={save} className="space-y-6">
        <Panel>
          <PanelTitle title="Profile" />
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Your name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Target role</Label>
              <Input
                id="role"
                value={form.targetRole}
                onChange={(e) => setForm({ ...form, targetRole: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Default interview language</Label>
              <Select
                value={form.language}
                onValueChange={(v) => setForm({ ...form, language: v as LangCode })}
              >
                <SelectTrigger className="h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LANGUAGES.map((l) => (
                    <SelectItem key={l.code} value={l.code}>
                      {l.native}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelTitle title="Voice" />
          <p className="text-sm text-muted-foreground">
            The live interviewer speaks through Gnani Timbre. Microphone audio is transcribed by
            Gnani Prisma.
          </p>
        </Panel>

        <div className="flex justify-end">
          <Button type="submit" variant="hero">
            Save changes
          </Button>
        </div>
      </form>

      <Panel>
        <PanelTitle
          title="Your data"
          description="The backend stores interview transcripts and reports. This browser also keeps a local report index."
        />
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(sessions, null, 2)], { type: "application/json" }),
              );
              const a = document.createElement("a");
              a.href = url;
              a.download = "interviewmirror-sessions.json";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download /> Export all interviews
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                className="text-destructive hover:bg-destructive-soft hover:text-destructive"
              >
                <Trash2 /> Delete all interviews
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete all interviews?</AlertDialogTitle>
                <AlertDialogDescription>
                  This removes {sessions.length} report links from this browser. Backend records are
                  managed separately.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    actions.clearSessions();
                    toast("All interviews deleted");
                  }}
                >
                  Delete all
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </Panel>
    </div>
  );
}
