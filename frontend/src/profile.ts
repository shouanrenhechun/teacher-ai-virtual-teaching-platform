import type { VirtualStudent } from './types';
export function profileTags(student: VirtualStudent): string[] {
  const cautious = /谨慎|低自信|确认/.test(student.personality_description) || student.confidence < 0.5;
  return [cautious ? '较谨慎' : '表达较有信心', student.initiative < 0.5 ? '倾向确认' : '愿意尝试表达', cautious ? '较少主动猜测' : '愿意尝试猜测'];
}
