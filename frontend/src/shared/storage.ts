import type { User } from './types';

export const authStore = {
  user(): User | null { try { return JSON.parse(localStorage.getItem('pai_candidate_user') || 'null'); } catch { return null; } },
  token(): string { return localStorage.getItem('pai_candidate_token') || ''; },
  save(user: User, token: string, _legacyAdminKey?: string) { localStorage.setItem('pai_candidate_user', JSON.stringify(user)); localStorage.setItem('pai_candidate_token', token); if (user.role === 'admin' || user.role === 'platform_admin') localStorage.setItem('pai_admin_key', token); },
  clear() { ['pai_candidate_user','pai_candidate_token','pai_candidate_last_lookup','pai_admin_key'].forEach(k => localStorage.removeItem(k)); sessionStorage.removeItem('pai_admin_key'); },
};
