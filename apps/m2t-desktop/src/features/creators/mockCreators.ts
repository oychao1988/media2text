export type MockCreator = {
  id: string;
  initial: string;
  name: string;
  sub: string;
  light: 'green' | 'red' | 'yellow' | 'gray';
  abbr: string;
  ariaLabel: string;
};

export const MOCK_CREATORS: MockCreator[] = [
  {
    id: 'hexue',
    initial: '何',
    name: '何同学',
    sub: 'douyin · 录制 01:24:08',
    light: 'green',
    abbr: '录',
    ariaLabel: '录制中',
  },
  {
    id: 'laofanqie',
    initial: '老',
    name: '老番茄',
    sub: 'bilibili · 直播中',
    light: 'red',
    abbr: '播',
    ariaLabel: '在播未录',
  },
  {
    id: 'yingshi',
    initial: '飓',
    name: '影视飓风',
    sub: 'bilibili · STT 降级',
    light: 'yellow',
    abbr: '收',
    ariaLabel: '收尾中',
  },
  {
    id: 'liyongle',
    initial: '李',
    name: '李永乐老师',
    sub: 'douyin · 离线',
    light: 'gray',
    abbr: '离',
    ariaLabel: '离线',
  },
];
