import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  Ticket,
  Copy,
  Check,
  Ban,
  ShieldCheck,
  MailCheck,
  Link2,
  Loader2,
  Plus,
  UserCheck,
  UserX,
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

interface AdminUser {
  user_id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  email_verified: boolean;
  broker_connected: boolean;
  created_at: string;
}

interface Invite {
  id: number;
  code: string;
  note: string | null;
  max_uses: number;
  used_count: number;
  expires_at: string | null;
  revoked: boolean;
  usable: boolean;
  created_at: string;
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-4">
      <p className="metric-label">{label}</p>
      <p className="metric-value text-xl">{value}</p>
    </div>
  );
}

function CopyButton({ text, title }: { text: string; title: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="p-1 rounded text-text-muted hover:text-white transition-colors"
      title={title}
    >
      {copied ? <Check size={13} className="text-gain" /> : <Copy size={13} />}
    </button>
  );
}

export default function Admin() {
  const qc = useQueryClient();
  const [maxUses, setMaxUses] = useState(1);
  const [expiresDays, setExpiresDays] = useState<number | "">(30);
  const [note, setNote] = useState("");

  const { data: stats } = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: () => api.get("/admin/stats").then((r) => r.data),
  });
  const { data: users = [], isLoading: usersLoading } = useQuery<AdminUser[]>({
    queryKey: ["admin", "users"],
    queryFn: () => api.get("/admin/users").then((r) => r.data),
  });
  const { data: invites = [] } = useQuery<Invite[]>({
    queryKey: ["admin", "invites"],
    queryFn: () => api.get("/admin/invites").then((r) => r.data),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin"] });
  };

  const createInvite = useMutation({
    mutationFn: () =>
      api.post("/admin/invites", {
        max_uses: maxUses,
        expires_days: expiresDays === "" ? null : expiresDays,
        note,
      }),
    onSuccess: () => {
      setNote("");
      refresh();
    },
  });

  const revokeInvite = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/invites/${id}`),
    onSuccess: refresh,
  });

  const toggleActive = useMutation({
    mutationFn: (id: number) => api.post(`/admin/users/${id}/toggle-active`),
    onSuccess: refresh,
  });

  const signupLink = `${window.location.origin}/`;

  return (
    <motion.div
      key="admin"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Admin</h1>
        <p className="text-sm text-text-muted mt-0.5">Users and invite codes</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Users" value={stats?.total_users ?? "—"} />
        <StatCard label="Active" value={stats?.active_users ?? "—"} />
        <StatCard label="Email Verified" value={stats?.verified_users ?? "—"} />
        <StatCard label="Broker Connected" value={stats?.broker_connected ?? "—"} />
      </div>

      {/* Invites */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-2 border-b border-border pb-3">
          <Ticket size={15} className="text-accent" />
          <h2 className="text-sm font-semibold text-text-primary">Invite Codes</h2>
        </div>

        {/* Create form */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-text-muted mb-1">Max uses</label>
            <select
              value={maxUses}
              onChange={(e) => setMaxUses(parseInt(e.target.value))}
              className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              {[1, 5, 10, 25, 100].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Expires</label>
            <select
              value={expiresDays}
              onChange={(e) =>
                setExpiresDays(e.target.value === "" ? "" : parseInt(e.target.value))
              }
              className="px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
              <option value="">Never</option>
            </select>
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="block text-xs text-text-muted mb-1">Note (optional)</label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. NJIT trading club"
              className="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-slate-500 focus:outline-none focus:border-accent"
            />
          </div>
          <button
            onClick={() => createInvite.mutate()}
            disabled={createInvite.isPending}
            className="px-4 py-2 bg-accent hover:bg-accent/90 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {createInvite.isPending ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Plus size={13} />
            )}
            Create Invite
          </button>
        </div>

        {/* Invite list */}
        {invites.length === 0 ? (
          <p className="text-sm text-text-muted py-2">
            No invite codes yet. Users can still sign up with the env{" "}
            <code className="font-mono text-xs">SIGNUP_INVITE_CODE</code> if set.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted border-b border-border">
                  <th className="py-2 pr-4 font-medium">Code</th>
                  <th className="py-2 pr-4 font-medium">Note</th>
                  <th className="py-2 pr-4 font-medium">Uses</th>
                  <th className="py-2 pr-4 font-medium">Expires</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {invites.map((inv) => (
                  <tr key={inv.id} className="border-b border-border/50">
                    <td className="py-2.5 pr-4">
                      <span className="font-mono text-xs text-text-primary">{inv.code}</span>
                      <CopyButton text={inv.code} title="Copy code" />
                      <CopyButton
                        text={`${signupLink}?invite=${inv.code}`}
                        title="Copy signup link"
                      />
                    </td>
                    <td className="py-2.5 pr-4 text-text-muted text-xs">{inv.note ?? "—"}</td>
                    <td className="py-2.5 pr-4 font-mono text-xs">
                      {inv.used_count}/{inv.max_uses}
                    </td>
                    <td className="py-2.5 pr-4 text-xs text-text-muted">
                      {inv.expires_at
                        ? new Date(inv.expires_at).toLocaleDateString()
                        : "Never"}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span
                        className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          inv.usable ? "badge-gain" : "badge-loss"
                        )}
                      >
                        {inv.revoked
                          ? "Revoked"
                          : inv.usable
                          ? "Active"
                          : inv.used_count >= inv.max_uses
                          ? "Used up"
                          : "Expired"}
                      </span>
                    </td>
                    <td className="py-2.5 text-right">
                      {!inv.revoked && inv.usable && (
                        <button
                          onClick={() => revokeInvite.mutate(inv.id)}
                          className="p-1.5 rounded text-text-muted hover:text-loss hover:bg-loss/10 transition-colors"
                          title="Revoke invite"
                        >
                          <Ban size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Users */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-2 border-b border-border pb-3">
          <Users size={15} className="text-accent" />
          <h2 className="text-sm font-semibold text-text-primary">Users</h2>
        </div>

        {usersLoading ? (
          <div className="flex items-center gap-2 text-sm text-text-muted py-4">
            <Loader2 size={14} className="animate-spin" /> Loading users…
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted border-b border-border">
                  <th className="py-2 pr-4 font-medium">User</th>
                  <th className="py-2 pr-4 font-medium">Joined</th>
                  <th className="py-2 pr-4 font-medium">Flags</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id} className="border-b border-border/50">
                    <td className="py-2.5 pr-4">
                      <p className="text-text-primary">{u.full_name ?? u.email}</p>
                      {u.full_name && <p className="text-xs text-text-muted">{u.email}</p>}
                    </td>
                    <td className="py-2.5 pr-4 text-xs text-text-muted">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2">
                        {u.is_admin && (
                          <span title="Admin">
                            <ShieldCheck size={14} className="text-accent" />
                          </span>
                        )}
                        {u.email_verified && (
                          <span title="Email verified">
                            <MailCheck size={14} className="text-gain" />
                          </span>
                        )}
                        {u.broker_connected && (
                          <span title="Broker connected">
                            <Link2 size={14} className="text-gain" />
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 pr-4">
                      <span
                        className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          u.is_active ? "badge-gain" : "badge-loss"
                        )}
                      >
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="py-2.5 text-right">
                      {!u.is_admin && (
                        <button
                          onClick={() => toggleActive.mutate(u.user_id)}
                          className={cn(
                            "p-1.5 rounded transition-colors",
                            u.is_active
                              ? "text-text-muted hover:text-loss hover:bg-loss/10"
                              : "text-text-muted hover:text-gain hover:bg-gain/10"
                          )}
                          title={u.is_active ? "Disable account" : "Enable account"}
                        >
                          {u.is_active ? <UserX size={13} /> : <UserCheck size={13} />}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </motion.div>
  );
}
