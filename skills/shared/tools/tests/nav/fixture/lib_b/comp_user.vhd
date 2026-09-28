library ieee;
use ieee.std_logic_1164.all;

entity comp_user is
  port (
    clk : in std_ulogic
  );
end entity;

architecture rtl of comp_user is
  component leaf is
    generic (
      width : positive := 8
    );
    port (
      clk : in std_ulogic;
      d : in std_ulogic_vector(width - 1 downto 0);
      q : out std_ulogic_vector(width - 1 downto 0)
    );
  end component;

  signal d, q : std_ulogic_vector(7 downto 0);
begin
  leaf_comp_inst : leaf
    port map (
      clk => clk,
      d => d,
      q => q
    );
end architecture;
