// Scores are provider estimates out of 100. Exactly 95 does not advance.
function accentProgression(phrases, currentId, accuracy, completed) {
  if (typeof accuracy !== 'number' || !Number.isFinite(accuracy) || accuracy <= 95 || accuracy > 100) return null;
  const ids = phrases.map(phrase => phrase.id);
  if (!ids.includes(currentId)) return null;
  const mastered = new Set(completed); mastered.add(currentId);
  const index = ids.indexOf(currentId);
  const ordered = [...ids.slice(index + 1), ...ids.slice(0, index)];
  const nextId = ordered.find(id => !mastered.has(id));
  return {completed: [...mastered], nextId: nextId || ordered[0] || null, roundComplete: !nextId};
}
if (typeof module !== 'undefined') module.exports = {accentProgression};
