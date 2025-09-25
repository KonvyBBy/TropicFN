
import { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export default function Card({ children, className = '', hover = false }: CardProps) {
  const hoverClass = hover ? 'hover:shadow-2xl hover:shadow-purple-500/10 hover:scale-105 hover:-translate-y-2 transition-all duration-500' : '';
  
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl shadow-xl ${hoverClass} ${className}`}>
      {children}
    </div>
  );
}