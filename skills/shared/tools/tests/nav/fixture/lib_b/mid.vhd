library ieee;
use ieee.std_logic_1164.all;

library lib_a;

entity mid is
  port (
    clk : in std_ulogic;
    d : in std_ulogic_vector(7 downto 0);
    q : out std_ulogic_vector(7 downto 0)
  );
end entity;

architecture rtl of mid is
begin
  leaf_inst : entity lib_a.leaf
    port map (
      clk => clk,
      d => d,
      q => q
    );
end architecture;
