export interface Account {
  id: string;
  title: string;
  price: number;
  skins: number;
  vbucks: number;
  xbLinked: boolean | null;
  psnLinked: boolean | null;
  hasEmail: boolean;
  isActive?: boolean;
  imageUrl?: string;
}

export const accounts: Account[] = [
  { id: "1", title: "Rogue Agent", price: 2.60, skins: 1, vbucks: 200, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "2", title: "78 Skins", price: 15.88, skins: 78, vbucks: 900, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "3", title: "Rogue Agent", price: 2.60, skins: 1, vbucks: 200, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "4", title: "Ffrb | 300 VB", price: 3.19, skins: 0, vbucks: 300, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "5", title: "191 Skins", price: 17.85, skins: 191, vbucks: 100, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "6", title: "120 Skins", price: 17.85, skins: 120, vbucks: 850, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "7", title: "74 Skins", price: 9.11, skins: 74, vbucks: 1750, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "8", title: "24 Skins | OG STW", price: 13.87, skins: 24, vbucks: 450, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "9", title: "John Wick", price: 2.60, skins: 1, vbucks: 100, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "10", title: "The Reaper | 126 Skins | Take The L", price: 20.08, skins: 126, vbucks: 650, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "11", title: "Ffrb | 1 Pickaxes, 2 Dances, 1 Gliders", price: 2.75, skins: 0, vbucks: 0, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "12", title: "Ffrb | 1 Pickaxes, 2 Dances, 2 Gliders", price: 4.05, skins: 0, vbucks: 0, xbLinked: true, psnLinked: true, hasEmail: true, isActive: true },
  { id: "13", title: "14 Скинов", price: 2.60, skins: 14, vbucks: 400, xbLinked: false, psnLinked: false, hasEmail: true },
  { id: "14", title: "20 Skins", price: 3.89, skins: 20, vbucks: 250, xbLinked: false, psnLinked: true, hasEmail: true },
  { id: "15", title: "15 Скинов", price: 3.28, skins: 15, vbucks: 1200, xbLinked: false, psnLinked: false, hasEmail: true },
  { id: "16", title: "Ffrb | 1 Skin", price: 2.75, skins: 1, vbucks: 200, xbLinked: true, psnLinked: true, hasEmail: true, isActive: true },
  { id: "17", title: "Ffrb | 100 VB | 2 Pickaxes, 2 Dances, 2 Gliders", price: 2.75, skins: 0, vbucks: 100, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "18", title: "Ffrb | 100 VB | 1 Pickaxes, 1 Dances, 2 Gliders", price: 2.75, skins: 0, vbucks: 100, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "19", title: "Ffrb | 300 VB", price: 3.17, skins: 0, vbucks: 300, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "20", title: "Mbk | 2 Skins", price: 2.75, skins: 2, vbucks: 100, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "21", title: "?", price: 12.73, skins: 15, vbucks: 550, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "22", title: "Ffrb | 7 Skins | 1000 VB", price: 3.19, skins: 7, vbucks: 1000, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "23", title: "Insajd | 1 Pickaxes, 3 Dances, 1 Gliders", price: 2.75, skins: 0, vbucks: 0, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "24", title: "Mbk | 1 Skin", price: 2.75, skins: 1, vbucks: 100, xbLinked: true, psnLinked: true, hasEmail: true },
  { id: "25", title: "OG Black Knight | 45 Skins", price: 34.99, skins: 45, vbucks: 2800, xbLinked: true, psnLinked: true, hasEmail: false },
  { id: "26", title: "Skull Trooper | 12 Skins", price: 18.50, skins: 12, vbucks: 500, xbLinked: true, psnLinked: false, hasEmail: true },
  { id: "27", title: "Recon Expert | Rare Account", price: 49.99, skins: 3, vbucks: 0, xbLinked: false, psnLinked: true, hasEmail: true },
  { id: "28", title: "Galaxy Skin | 67 Skins", price: 22.00, skins: 67, vbucks: 1500, xbLinked: true, psnLinked: true, hasEmail: true },
];

export const sortOptions = ["Default", "Cheap first", "Expensive first", "Newest", "Oldest"];

export const totalAccounts = 15629;
export const totalPages = 652;