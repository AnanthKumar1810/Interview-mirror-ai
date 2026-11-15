import type { Session } from "./types";

export interface TopicStat {
  topic: string;
  best: number;
  count: number;
  domainId: string;
}

/** Best score and number of attempts per topic across all sessions. */
export function topicStats(sessions: Session[]): TopicStat[] {
  const map = new Map<string, TopicStat>();
  for (const s of sessions) {
    for (const t of s.turns) {
      const cur = map.get(t.topic);
      if (cur) {
        cur.best = Math.max(cur.best, t.score);
        cur.count += 1;
      } else map.set(t.topic, { topic: t.topic, best: t.score, count: 1, domainId: s.domainId });
    }
  }
  return [...map.values()].sort((a, b) => b.best - a.best);
}

/** Missing ideas that came up most often, newest sessions first. */
export function recurringGaps(sessions: Session[], limit = 4) {
  const counts = new Map<string, { concept: string; count: number; topic: string }>();
  for (const s of sessions) {
    for (const t of s.turns) {
      for (const c of t.missingConcepts) {
        const cur = counts.get(c);
        if (cur) cur.count += 1;
        else counts.set(c, { concept: c, count: 1, topic: t.topic });
      }
    }
  }
  return [...counts.values()].sort((a, b) => b.count - a.count).slice(0, limit);
}
