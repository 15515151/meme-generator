/**
 * 图标统一从 lucide-react 重新导出，业务代码只从这里引用，
 * 以后换图标库时不用改各个页面。
 *
 * 对外保留 IconXxx 命名，同时把 IconProps 统一成 { size }，与原来的用法一致。
 */

import {
  Ban,
  Check,
  Code2,
  Download,
  Eye,
  Image as ImageIcon,
  Info,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Moon,
  Package,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  Sun,
  Trash2,
  X,
  type LucideIcon,
} from 'lucide-react'

type Props = { size?: number }

/** 把 lucide 图标的 size 默认值与调用方保持一致。 */
function withSize(Icon: LucideIcon, defaultSize = 16) {
  return function SizedIcon({ size = defaultSize }: Props) {
    return <Icon size={size} aria-hidden="true" />
  }
}

export const IconDashboard = withSize(LayoutDashboard, 17)
export const IconMeme = withSize(ImageIcon, 17)
export const IconRepo = withSize(Package, 17)
export const IconUpdate = withSize(RefreshCw, 17)
export const IconSettings = withSize(Settings, 17)

export const IconSearch = withSize(Search, 15)
export const IconPlus = withSize(Plus, 15)
export const IconRefresh = withSize(RefreshCw, 15)
export const IconCheck = withSize(Check, 14)
export const IconX = withSize(X, 16)
export const IconTrash = withSize(Trash2, 14)
export const IconDownload = withSize(Download, 14)
export const IconEye = withSize(Eye, 14)
export const IconInfo = withSize(Info, 15)
export const IconSun = withSize(Sun, 16)
export const IconMoon = withSize(Moon, 16)
export const IconLogout = withSize(LogOut, 16)
export const IconLock = withSize(KeyRound, 15)
export const IconServer = withSize(Server, 14)
export const IconBan = withSize(Ban, 14)
export const IconCode = withSize(Code2, 14)

export { Ban, Check, Code2, Download, Eye, Info, Moon, Plus, Search, Server, Settings, Sun, Trash2, X }
export type { LucideIcon }
